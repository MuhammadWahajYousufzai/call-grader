"""Retention worker: 15-day audio deletion + 7-day debug artifact cleanup."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from appwrite.query import Query

from app.appwrite import client as aw
from app.appwrite import repos
from app.config.settings import get_settings

AUDIO_DONE_STATES = (
    "TRANSCRIBED", "ROMANIZATION_PENDING", "ROMANIZING", "ROMANIZATION_FAILED",
    "ROMANIZED", "GRADING_PENDING", "GRADING", "GRADING_FAILED", "COMPLETE",
    "NO_SPEECH", "UNGRADABLE",
)


def cleanup_expired_audio(dry_run: bool = False) -> dict:
    s = get_settings()
    now = datetime.now(UTC).isoformat()
    rows = repos.list_docs("calls", [
        Query.is_not_null("recording_storage_file_id") if hasattr(Query, "is_not_null") else Query.not_equal("recording_storage_file_id", ""),
        Query.less_than_equal("recording_retention_due_at", now),
        Query.limit(100),
    ], limit=100)
    deleted = skipped = 0
    for c in rows:
        if not c.get("recording_storage_file_id") or c.get("recording_deleted_at"):
            continue
        status = c.get("pipeline_status", "")
        # race safety: only delete past audio-required stages or terminal states
        active = repos.list_docs("processing_jobs", [
            Query.equal("call_id", c.get("$id", "")),
            Query.equal("status", "LEASED"),
            Query.limit(5),
        ], limit=5)
        if active:
            skipped += 1
            continue
        # Never remove audio while transcription still needs it, including a
        # failed transcription that is waiting for a durable retry.
        if status not in AUDIO_DONE_STATES:
            skipped += 1
            continue
        if not dry_run:
            try:
                aw.storage().delete_file(bucket_id=aw.bucket_id(), file_id=c["recording_storage_file_id"])
            except Exception:
                skipped += 1
                continue
            repos.update_call(c["$id"], {
                "recording_storage_file_id": "",
                "recording_deleted_at": datetime.now(UTC).isoformat(),
                "recording_delete_reason": f"retention_{s.AUDIO_RETENTION_DAYS}d",
            })
        deleted += 1
    return {"deleted": deleted, "skipped_active": skipped}


def cleanup_debug_artifacts() -> dict:
    import time

    s = get_settings()
    root = Path(s.DEBUG_ARTIFACT_DIR)
    if not root.exists():
        return {"deleted": 0}
    cutoff = time.time() - s.DEBUG_ARTIFACT_RETENTION_DAYS * 86400
    n = 0
    for p in root.iterdir():
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                n += 1
        except Exception:
            continue
    return {"deleted": n}
