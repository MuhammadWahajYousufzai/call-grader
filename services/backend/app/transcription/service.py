"""Transcription service — direct OpenAI Audio API (NOT the Agents SDK).

Primary: gpt-4o-transcribe-diarize with response_format diarized_json.
Fallback: configurable gpt-transcribe path.
"""

from __future__ import annotations

from pathlib import Path

from openai import OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config.settings import get_settings


def _client() -> OpenAI:
    s = get_settings()
    return OpenAI(api_key=s.OPENAI_API_KEY, timeout=s.OPENAI_TIMEOUT_SECONDS)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=60),
       retry=retry_if_exception_type((TimeoutError, ConnectionError)))
def transcribe_file(path: Path, language_hint: str = "ur") -> list[dict]:
    """Return [{speaker, start, end, text}]. Raises on permanent failure."""
    s = get_settings()
    client = _client()
    last_err: Exception | None = None
    for i, model in enumerate((s.OPENAI_TRANSCRIBE_MODEL, s.OPENAI_TRANSCRIBE_FALLBACK_MODEL)):
        try:
            with open(path, "rb") as f:
                fmt = "diarized_json" if i == 0 else "json"
                kwargs: dict = {"file": f, "model": model, "response_format": fmt}
                # chunking auto where supported
                try:
                    resp = client.audio.transcriptions.create(**kwargs, chunking_strategy="auto")  # type: ignore[call-arg]
                except TypeError:
                    f.seek(0)
                    resp = client.audio.transcriptions.create(file=f, model=model, response_format=fmt)  # type: ignore[call-arg]
            segments = _to_segments(resp)
            return segments  # Empty success means genuine silence; never fabricate speech.
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if "rate" in msg or "429" in msg or "timeout" in msg or "overload" in msg or "5" in msg[:2]:
                continue  # try fallback model
            # for unknown models etc, try fallback once
            continue
    raise RuntimeError(f"Transcription failed for {path.name}: {last_err}")


def _to_segments(resp) -> list[dict]:
    data = resp
    if hasattr(resp, "model_dump"):
        data = resp.model_dump()
    elif hasattr(resp, "to_dict"):
        data = resp.to_dict()
    if isinstance(data, dict):
        segs = data.get("segments") or data.get("results") or []
        out = []
        for i, sg in enumerate(segs):
            if isinstance(sg, dict):
                out.append({
                    "speaker": str(sg.get("speaker", sg.get("speaker_label", f"SPEAKER_{i % 2:02d}"))),
                    "start": float(sg.get("start", sg.get("start_time", 0)) or 0),
                    "end": float(sg.get("end", sg.get("end_time", 0)) or 0),
                    "text": str(sg.get("text", "")),
                })
        if out:
            return out
        txt = data.get("text", "")
        if txt:
            return [{"speaker": "SPEAKER_00", "start": 0.0, "end": 0.0, "text": str(txt)}]
    txt = getattr(resp, "text", "")
    if txt:
        return [{"speaker": "SPEAKER_00", "start": 0.0, "end": 0.0, "text": str(txt)}]
    return []


def assign_roles(segments: list[dict], agent_identifier: str = "") -> list[dict]:
    """Heuristic speaker-role assignment with uncertainty flags. Never confidently mislabel."""
    if not segments:
        return segments
    # Majority heuristic: first speaker is often the agent on outbound, customer on inbound.
    # Without channel metadata we keep generic IDs when uncertain.
    counts: dict[str, int] = {}
    for sg in segments:
        counts[sg["speaker"]] = counts.get(sg["speaker"], 0) + 1
    ordered = sorted(counts, key=lambda k: -counts[k])
    role_map: dict[str, tuple[str, float]] = {}
    if len(ordered) >= 2:
        # Greeting heuristic: segment containing salam/addressing rice -> likely Agent
        first_text = " ".join(s.get("text", "") for s in segments[:3]).lower()
        agent_like = any(w in first_text for w in ("yousuf", "rice", "assalam", "salam", "ji farmaiye", "farmaiye"))
        if agent_like:
            first_sp = segments[0]["speaker"]
            other = ordered[0] if ordered[0] != first_sp else ordered[1]
            role_map[first_sp] = ("Agent", 0.65)
            role_map[other] = ("Customer", 0.65)
        else:
            role_map[ordered[0]] = ("Agent", 0.4)
            role_map[ordered[1]] = ("Customer", 0.4)
    elif len(ordered) == 1:
        role_map[ordered[0]] = ("Unknown", 0.2)
    for sg in segments:
        role, conf = role_map.get(sg["speaker"], ("Unknown", 0.2))
        sg["role"] = role
        sg["confidence"] = conf
        sg["uncertain"] = conf < 0.6
    return segments
