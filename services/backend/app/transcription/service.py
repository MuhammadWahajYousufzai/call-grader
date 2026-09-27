"""Gemini transcription and cautious speaker-role assignment."""

from __future__ import annotations

from pathlib import Path


def transcribe_file(path: Path, language_hint: str = "ur") -> list[dict]:
    """Native Gemini diarization, word timestamps and verbatim multilingual speech."""
    from app.ai.gemini import transcribe
    return transcribe(path)


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
