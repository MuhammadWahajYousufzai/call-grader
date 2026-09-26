"""Pipeline worker: DOWNLOAD -> TRANSCRIBE -> ROMANIZE -> GRADE -> report update.

Crash-safe: each phase checkpoints in Appwrite; failures resume at failed step.
"""

from __future__ import annotations

import json
import tempfile
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from appwrite.query import Query

from app.appwrite import client as aw
from app.appwrite import repos
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.jobs.queue import claim_next_job, complete_job, fail_job, recover_stale_leases

log = get_logger("worker")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def ensure_dirs() -> Path:
    s = get_settings()
    p = Path(s.LOCAL_AUDIO_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup_processed_audio_if_expired(call: dict) -> None:
    due = call.get("recording_retention_due_at")
    if due and datetime.fromisoformat(due.replace("Z", "+00:00")) <= datetime.now(UTC):
        from app.retention.worker import cleanup_expired_audio

        cleanup_expired_audio()


# ---- phase implementations ----

def do_download(call: dict) -> None:
    """Download recording via Jazz (real path) or reuse existing storage file."""

    from appwrite.input_file import InputFile

    from app.jazz.client import JazzClient
    from app.jazz.downloader import verify_audio

    s = get_settings()
    call_id = call["$id"]
    if call.get("recording_storage_file_id"):
        repos.update_call(call_id, {"pipeline_status": "TRANSCRIPTION_PENDING"})
        repos.ensure_job("TRANSCRIBE", call_id, call.get("reporting_date", ""))
        return
    repos.update_call(call_id, {"pipeline_status": "DOWNLOADING"})
    # NOTE: the Jazz portal exposes per-row recording links discovered at sync time.
    # The sync persists row URL in raw_jazz_row; here we re-resolve via a light
    # authenticated session and download with verification.
    try:
        raw = json.loads(call.get("raw_jazz_row", "{}") or "{}")
        url = raw.get("url", "")
    except Exception:
        url = ""
    if not url:
        repos.update_call(call_id, {"pipeline_status": "NO_RECORDING", "last_error_message": "No recording URL from Jazz row"})
        return
    try:
        with JazzClient(state_dir=str(Path(s.PLAYWRIGHT_STATE_DIR) / "download")) as client:
            client.ensure_auth(run_id=call_id[:8])
            with tempfile.TemporaryDirectory() as td:
                dest = Path(td) / f"{call_id}.wav"
                if not client.download_recording(url, dest):
                    repos.update_call(call_id, {"pipeline_status": "NO_RECORDING",
                                                "recording_available": False})
                    return
                info = verify_audio(dest, expected_duration=int(call.get("duration_seconds", 0) or 0))
                # upload to private Appwrite bucket
                # A deterministic file ID makes a crash after upload safe: the
                # retry finds the same private object instead of duplicating it.
                try:
                    up = aw.storage().create_file(
                        bucket_id=aw.bucket_id(), file_id=call_id,
                        file=InputFile.from_path(str(dest)),
                    )
                except Exception:
                    remote = aw.storage().get_file_download(bucket_id=aw.bucket_id(), file_id=call_id)
                    from hashlib import sha256

                    if sha256(bytes(remote)).hexdigest() != info["sha256"]:
                        raise RuntimeError("Existing Appwrite recording differs from Jazz audio") from None
                    up = {"$id": call_id}
                fid = (up.get("$id") or up.get("id")) if isinstance(up, dict) else getattr(up, "id", "")
                if not fid:
                    raise RuntimeError("Appwrite upload returned no file ID")
                from datetime import timedelta

                actual = datetime.fromisoformat(call["actual_started_at"].replace("Z", "+00:00"))
                due = (actual + timedelta(days=s.AUDIO_RETENTION_DAYS)).isoformat()
                repos.update_call(call_id, {
                    "pipeline_status": "AUDIO_VALIDATED",
                    "recording_storage_file_id": fid,
                    "recording_sha256": info["sha256"],
                    "recording_downloaded_at": _utcnow(),
                    "recording_retention_due_at": due,
                })
                repos.ensure_job("TRANSCRIBE", call_id, call.get("reporting_date", ""))
    except Exception as e:
        repos.update_call(call_id, {"pipeline_status": "DOWNLOAD_FAILED",
                                    "last_error_code": "JAZZ_DOWNLOAD_FAILED",
                                    "last_error_message": str(e)[:1000]})
        raise


def _download_storage_to_tmp(call: dict, tmpdir: Path) -> Path:
    fid = call.get("recording_storage_file_id", "")
    if not fid:
        raise RuntimeError("AUDIO_INVALID: no stored recording")
    dest = tmpdir / f"{call['$id']}.wav"
    data = aw.storage().get_file_download(bucket_id=aw.bucket_id(), file_id=fid)
    dest.write_bytes(data if isinstance(data, (bytes, bytearray)) else bytes(data))
    return dest


def do_transcribe(call: dict) -> None:
    from app.audio.normalize import normalize_for_transcription, split_for_upload
    from app.transcription.service import assign_roles, transcribe_file

    s = get_settings()
    call_id = call["$id"]
    repos.update_call(call_id, {"pipeline_status": "TRANSCRIBING"})
    tmpdir = ensure_dirs()
    src = _download_storage_to_tmp(call, tmpdir)
    norm = tmpdir / f"{call_id}_norm.mp3"
    try:
        ready = normalize_for_transcription(src, norm)
    except Exception:
        ready = src
    chunks = split_for_upload(ready)
    all_segs: list[dict] = []
    for chunk_path, offset in chunks:
        segs = transcribe_file(chunk_path)
        for sg in segs:
            sg["start"] = float(sg.get("start", 0) or 0) + offset
            sg["end"] = float(sg.get("end", 0) or 0) + offset
            all_segs.append(sg)
    if not all_segs:
        for path in {src, norm}:
            path.unlink(missing_ok=True)
        repos.update_call(call_id, {"pipeline_status": "NO_SPEECH",
                                    "last_error_code": "", "last_error_message": ""})
        if call.get("reporting_date"):
            repos.ensure_report_job(call["reporting_date"])
        return
    all_segs = assign_roles(all_segs, call.get("jazz_agent_identifier", ""))
    # persist
    docs = [{
        "sequence": i,
        "speaker_raw": sg.get("speaker", ""),
        "speaker_role": sg.get("role", "Unknown") if sg.get("role") in ("Agent", "Customer") else "Unknown",
        "speaker_confidence": float(sg.get("confidence", 0) or 0),
        "uncertain": bool(sg.get("uncertain", True)),
        "start_seconds": float(sg.get("start", 0) or 0),
        "end_seconds": float(sg.get("end", 0) or 0),
        "raw_text": str(sg.get("text", ""))[:4000],
        "roman_urdu_text": "",
        "id": f"seg_{i}",
    } for i, sg in enumerate(all_segs)]
    # clear old then save
    for old in repos.get_segments(call_id):
        try:
            repos.delete_doc("transcript_segments", old["$id"])
        except Exception:
            pass
    repos.save_segments(call_id, [{k: v for k, v in d.items() if k != "id"} for d in docs])
    repos.update_call(call_id, {"pipeline_status": "ROMANIZATION_PENDING",
                                "transcription_model": s.OPENAI_TRANSCRIBE_MODEL})
    repos.ensure_job("ROMANIZE", call_id, call.get("reporting_date", ""))
    try:
        src.unlink(missing_ok=True)
    except Exception:
        pass


def do_romanize(call: dict) -> None:
    from app.ai.workflows import romanize_segments

    call_id = call["$id"]
    repos.update_call(call_id, {"pipeline_status": "ROMANIZING"})
    segs = repos.get_segments(call_id)
    normed = romanize_segments([
        {"id": f"seg_{s.get('sequence', i)}", "speaker_role": s.get("speaker_role", "Unknown"),
         "start_seconds": s.get("start_seconds", 0), "end_seconds": s.get("end_seconds", 0),
         "raw_text": s.get("raw_text", "")} for i, s in enumerate(segs)
    ])
    by_seq = {int(n["id"].split("_")[1]): n["roman_urdu_text"] for n in normed if "_" in n.get("id", "")}
    for sg in segs:
        txt = by_seq.get(int(sg.get("sequence", -1)), sg.get("raw_text", ""))
        repos.update_doc("transcript_segments", sg["$id"], {"roman_urdu_text": (txt or "")[:4000]})
    repos.update_call(call_id, {"pipeline_status": "GRADING_PENDING"})
    repos.ensure_job("GRADE", call_id, call.get("reporting_date", ""))


def do_grade(call: dict) -> None:
    import json as _json

    from app.ai.prompts.grading import GRADING_PROMPT_VERSION, RUBRIC_VERSION
    from app.ai.workflows import grade_call

    s = get_settings()
    call_id = call["$id"]
    repos.update_call(call_id, {"pipeline_status": "GRADING"})
    segs = repos.get_segments(call_id)
    seg_dicts = [{
        "id": f"seg_{sg.get('sequence', i)}", "speaker_role": sg.get("speaker_role", "Unknown"),
        "start_seconds": sg.get("start_seconds", 0), "end_seconds": sg.get("end_seconds", 0),
        "raw_text": sg.get("raw_text", ""), "roman_urdu_text": sg.get("roman_urdu_text", "") or sg.get("raw_text", ""),
    } for i, sg in enumerate(segs)]
    rules_rows = repos.list_docs("business_rules", limit=50)
    rules = "\n".join(f"{r.get('key')}: {r.get('value', '')}" for r in rules_rows)
    try:
        result = grade_call(seg_dicts, {
            "direction": call.get("direction"), "duration_seconds": call.get("duration_seconds"),
            "agent": call.get("agent_name_snapshot"), "customer": "REDACTED",
        }, rules)
    except ValueError as exc:
        if str(exc) != "No applicable dimensions to score":
            raise
        repos.update_call(call_id, {"pipeline_status": "UNGRADABLE",
                                    "last_error_code": "INSUFFICIENT_GRADING_EVIDENCE",
                                    "last_error_message": "No applicable grading dimensions in this transcript"})
        if call.get("reporting_date"):
            repos.ensure_report_job(call["reporting_date"])
        return
    repos.save_grade({
        "call_id": call_id,
        "overall_score": float(result.get("overall_score", 0) or 0),
        "call_type": str(result.get("call_type", "other")),
        "primary_intent": str(result.get("primary_intent", "other")),
        "grader_model": s.OPENAI_GRADING_MODEL,
        "grading_prompt_version": GRADING_PROMPT_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "result_json": _json.dumps(result)[:65000],
    })
    repos.update_call(call_id, {"pipeline_status": "COMPLETE", "last_error_code": "",
                                "last_error_message": "", "grader_model": s.OPENAI_GRADING_MODEL,
                                "grading_prompt_version": GRADING_PROMPT_VERSION,
                                "rubric_version": RUBRIC_VERSION})
    rd = call.get("reporting_date", "")
    if rd:
        repos.ensure_report_job(rd)


def do_report(reporting_date: str) -> None:
    from app.ai.workflows import daily_coaching_summary
    from app.reporting.compute import compute_report

    calls = []
    offset = 0
    while True:
        batch = repos.list_docs("calls", [Query.equal("reporting_date", reporting_date)],
                                limit=100, offset=offset)
        calls.extend(batch)
        if len(batch) < 100:
            break
        offset += len(batch)
    grades = {}
    highlights = []
    for call in calls:
        grade = repos.get_grade(call["$id"])
        if grade:
            try:
                result = json.loads(grade.get("result_json", "{}") or "{}")
                grades[call["$id"]] = result
                if len(highlights) < 10:
                    highlights.append(result)
            except Exception:
                continue
    metrics = compute_report(calls, grades, threshold=get_settings().LOW_SCORE_THRESHOLD)
    status = "COMPLETE" if not metrics["still_processing"] and not metrics["processing_failures"] else (
        "COMPLETE_WITH_ERRORS" if metrics["processing_failures"] else "PROCESSING")
    repos.save_report(reporting_date, status, metrics, coaching_summary="")
    if status == "COMPLETE" and highlights:
        summary = daily_coaching_summary(metrics, highlights)
        repos.save_report(reporting_date, status, metrics, summary)


HANDLERS = {"DOWNLOAD": do_download, "TRANSCRIBE": do_transcribe, "ROMANIZE": do_romanize, "GRADE": do_grade}

PHASE_ORDER = {"DOWNLOAD": 0, "TRANSCRIBE": 1, "ROMANIZE": 2, "GRADE": 3}
STATE_PHASE = {
    "DISCOVERED": 0, "METADATA_SAVED": 0, "DOWNLOAD_PENDING": 0, "DOWNLOADING": 0,
    "DOWNLOAD_FAILED": 0, "DOWNLOADED": 1, "AUDIO_VALIDATED": 1,
    "TRANSCRIPTION_PENDING": 1, "TRANSCRIBING": 1, "TRANSCRIPTION_FAILED": 1,
    "TRANSCRIBED": 2, "ROMANIZATION_PENDING": 2, "ROMANIZING": 2,
    "ROMANIZATION_FAILED": 2, "ROMANIZED": 3, "GRADING_PENDING": 3,
    "GRADING": 3, "GRADING_FAILED": 3,
}
JOB_FOR_PHASE = ("DOWNLOAD", "TRANSCRIBE", "ROMANIZE", "GRADE")


def recover_incomplete_calls() -> int:
    """Repair checkpoints left between a call update and its next job enqueue."""
    restored = 0
    offset = 0
    days: dict[str, list[str]] = {}
    while True:
        batch = repos.list_docs("calls", limit=100, offset=offset)
        for call in batch:
            status = call.get("pipeline_status", "")
            rd = call.get("reporting_date", "")
            if rd:
                days.setdefault(rd, []).append(status)
            phase = STATE_PHASE.get(status)
            if phase is None:
                continue
            if phase == 0 and not call.get("recording_available"):
                continue
            jobs = repos.list_docs("processing_jobs", [Query.equal("call_id", call["$id"])], limit=100)
            kind = JOB_FOR_PHASE[phase]
            if any(j.get("job_type") == kind and j.get("status") in ("QUEUED", "LEASED", "FAILED")
                   for j in jobs):
                continue
            repos.ensure_job(kind, call["$id"], call.get("reporting_date", ""))
            restored += 1
        if len(batch) < 100:
            break
        offset += len(batch)
    for rd, statuses in days.items():
        if "COMPLETE" in statuses and all(s in ("COMPLETE", "NO_RECORDING", "NO_SPEECH",
                                              "UNGRADABLE", "NOT_ELIGIBLE")
                                         for s in statuses):
            report = repos.get_report(rd)
            if not report or not report.get("coaching_summary"):
                repos.ensure_report_job(rd)
    return restored


def process_one(worker_id: str) -> bool:
    job = claim_next_job(worker_id)
    if not job:
        return False
    jtype = job.get("job_type", "")
    call_id = job.get("call_id", "")
    try:
        if jtype == "REPORT":
            do_report(job.get("reporting_date", ""))
            complete_job(job["$id"])
            return True
        call = repos.get_doc("calls", call_id) if call_id else None
        if call_id and not call:
            fail_job(job["$id"], "call row missing", retryable=False)
            return True
        handler = HANDLERS.get(jtype)
        if not handler:
            fail_job(job["$id"], f"unknown job type {jtype}", retryable=False)
            return True
        status = call.get("pipeline_status", "") if call else ""
        if status in ("COMPLETE", "NO_RECORDING", "NO_SPEECH", "UNGRADABLE", "NOT_ELIGIBLE") or (
            status in STATE_PHASE and STATE_PHASE[status] > PHASE_ORDER[jtype]
        ):
            complete_job(job["$id"])
            return True
        handler(call)
        complete_job(job["$id"])
        # Release the lease before retention checks; active jobs protect audio.
        if jtype in ("TRANSCRIBE", "GRADE"):
            try:
                cleanup_processed_audio_if_expired(call)
            except Exception:
                log.warning("Expired audio cleanup deferred to scheduler")
    except Exception as e:
        msg = str(e)
        retryable = not any(k in msg for k in ("AUDIO_INVALID", "schema", "unknown job"))
        if call_id:
            try:
                c = repos.get_doc("calls", call_id)
                if c:
                    rc = int(c.get("retry_count", 0) or 0) + 1
                    repos.update_call(call_id, {"retry_count": rc})
            except Exception:
                pass
        outcome = fail_job(job["$id"], msg[:2000], retryable=retryable)
        if call_id:
            phase = {"DOWNLOAD": "DOWNLOAD", "TRANSCRIBE": "TRANSCRIPTION",
                     "ROMANIZE": "ROMANIZATION", "GRADE": "GRADING"}.get(jtype, "")
            if phase:
                repos.update_call(call_id, {
                    "pipeline_status": f"{phase}_{'FAILED' if outcome == 'FAILED' else 'PENDING'}",
                    "last_error_code": getattr(e, "code", f"{phase}_FAILED"),
                    "last_error_message": msg[:1000],
                })
                if job.get("reporting_date"):
                    repos.ensure_report_job(job["reporting_date"])
    finally:
        if jtype == "TRANSCRIBE" and call_id:
            for path in ensure_dirs().glob(f"{call_id}*"):
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
    return True


def main() -> None:
    worker_id = f"worker-{uuid.uuid4().hex[:6]}"
    s = get_settings()
    recover_stale_leases()
    recover_incomplete_calls()
    while True:
        try:
            recover_stale_leases()
            if not process_one(worker_id):
                time.sleep(s.WORKER_POLL_INTERVAL_SECONDS)
        except KeyboardInterrupt:
            break
        except Exception:
            time.sleep(s.WORKER_POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
