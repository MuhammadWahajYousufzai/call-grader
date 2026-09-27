"""Checkpoint audio chunks and Roman Urdu batches between Function executions."""

import json
import subprocess
from hashlib import sha256

from app.appwrite import repos
from app.config.settings import get_settings


class ContinueJob(Exception):
    """A durable checkpoint is saved; requeue this phase without counting a failure."""


def finish_transcription(call):
    call_id = call["$id"]
    has_speech = bool(repos.get_segments(call_id))
    repos.update_call(call_id, {
        "pipeline_status": "ROMANIZATION_PENDING" if has_speech else "NO_SPEECH",
        "transcription_model": get_settings().GEMINI_TRANSCRIBE_MODEL,
        "last_error_code": "", "last_error_message": "",
    })
    if has_speech:
        repos.ensure_job("ROMANIZE", call_id, call.get("reporting_date", ""))
    elif call.get("reporting_date"):
        repos.ensure_report_job(call["reporting_date"])


def transcribe_chunk(call):
    from app.jazz.downloader import verify_audio
    from app.jobs.worker import _download_storage_to_tmp, ensure_dirs
    from app.transcription.service import assign_roles, transcribe_file

    call_id = call["$id"]
    key = "transcription_progress_" + call_id
    value = repos.get_setting(key)
    progress = json.loads(value) if value else None
    model = get_settings().GEMINI_TRANSCRIBE_MODEL
    if progress and progress.get("model") == model and progress.get("sha") == call.get("recording_sha256") and progress.get("done"):
        finish_transcription(call)
        return
    if not progress or progress.get("sha") != call.get("recording_sha256") or progress.get("model") != model:
        for segment in repos.get_segments(call_id):
            repos.delete_doc("transcript_segments", segment["$id"])
        progress = {"sha": call.get("recording_sha256"), "model": model, "chunk": 0, "done": False}
        repos.set_setting(key, json.dumps(progress))
    repos.update_call(call_id, {"pipeline_status": "TRANSCRIBING"})
    directory = ensure_dirs()
    source = _download_storage_to_tmp(call, directory)
    duration = verify_audio(source)["duration"]
    offset = progress["chunk"] * 600
    chunk = directory / f"{call_id}_chunk.mp3"
    subprocess.run(["ffmpeg", "-y", "-ss", str(offset), "-i", str(source),
                    "-t", "600", "-ac", "1", "-ar", "16000", "-b:a", "64k", str(chunk)],
                   check=True, capture_output=True, timeout=120)
    segments = assign_roles(transcribe_file(chunk), call.get("jazz_agent_identifier", ""))
    # IDs include chunk and sequence: a crash during persistence can safely
    # replay this chunk. Delete incomplete chunk rows before rewriting it.
    prefix = progress["chunk"] * 10000
    for old in repos.get_segments(call_id):
        if prefix <= old["sequence"] < prefix + 10000:
            repos.delete_doc("transcript_segments", old["$id"])
    for index, segment in enumerate(segments):
        sequence = prefix + index
        row_id = "seg_" + sha256(f"{call_id}:{sequence}".encode()).hexdigest()[:28]
        repos.create_doc("transcript_segments", {
            "call_id": call_id, "sequence": sequence,
            "speaker_raw": f"chunk{progress['chunk']}:{segment.get('speaker', '')}",
            "speaker_role": segment.get("role", "Unknown"),
            "speaker_confidence": float(segment.get("confidence", 0)),
            "uncertain": bool(segment.get("uncertain", True)),
            "start_seconds": float(segment.get("start", 0)) + offset,
            "end_seconds": float(segment.get("end", 0)) + offset,
            "raw_text": str(segment.get("text", ""))[:4000], "roman_urdu_text": "",
        }, row_id)
    progress["chunk"] += 1
    progress["done"] = progress["chunk"] * 600 >= duration
    repos.set_setting(key, json.dumps(progress))
    if not progress["done"]:
        raise ContinueJob()
    finish_transcription(call)


def romanize_batch(call):
    from app.ai.workflows import romanize_segments

    call_id = call["$id"]
    repos.update_call(call_id, {"pipeline_status": "ROMANIZING"})
    pending = [segment for segment in repos.get_segments(call_id)
               if not segment.get("roman_urdu_text") and segment.get("raw_text")]
    batch = []
    size = 0
    for segment in pending[:30]:
        if batch and size + len(segment["raw_text"]) > 10000:
            break
        size += len(segment["raw_text"])
        batch.append(segment)
    if batch:
        results = romanize_segments([
            {**segment, "id": f"seg_{segment['sequence']}"} for segment in batch])
        by_id = {result["id"]: result["roman_urdu_text"] for result in results}
        for segment in batch:
            text = by_id[f"seg_{segment['sequence']}"]
            if not text:
                raise RuntimeError("Romanizer returned empty text for speech")
            repos.update_doc("transcript_segments", segment["$id"], {"roman_urdu_text": text[:4000]})
    if len(pending) > len(batch):
        raise ContinueJob()
    repos.update_call(call_id, {"pipeline_status": "GRADING_PENDING"})
    repos.ensure_job("GRADE", call_id, call.get("reporting_date", ""))
