"""Async job queue abstraction over the Appwrite processing_jobs table.

Durable, lease-based, poll-driven. Redis/Valkey can replace this later
without changing callers (same function signatures).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from appwrite.query import Query

from app.appwrite import repos
from app.config.settings import get_settings
from app.domain.helpers import latest_processing_date


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def claim_next_job(worker_id: str, job_types: list[str] | None = None) -> dict | None:
    """Atomically-ish claim one QUEUED due job via lease. Stale leases recovered on read."""
    s = get_settings()
    # Finish already downloaded calls before opening another Jazz browser.
    for kind in (job_types or ["REPORT", "GRADE", "ROMANIZE", "TRANSCRIBE", "DOWNLOAD"]):
        queries: list[str] = [
            Query.equal("status", "QUEUED"),
            Query.equal("job_type", kind),
            Query.less_than_equal("reporting_date", latest_processing_date(_now()).isoformat()),
            Query.less_than_equal("next_attempt_at", _iso(_now())),
            Query.order_asc("next_attempt_at"),
        ]
        candidates = repos.list_docs("processing_jobs", queries, limit=10)
        for job in candidates:
            try:
                lease_until = _iso(_now() + timedelta(seconds=s.WORKER_LEASE_SECONDS))
                updated = repos.update_doc("processing_jobs", job["$id"], {
                    "status": "LEASED", "locked_by": worker_id,
                    "lock_expires_at": lease_until,
                })
                return updated
            except Exception:
                continue
    return None


def complete_job(job_id: str) -> None:
    repos.update_doc("processing_jobs", job_id, {"status": "DONE", "locked_by": "", "last_error": ""})


def fail_job(job_id: str, error: str, retryable: bool = True, retry_after: int = 0) -> str:
    from app.domain.helpers import backoff_delay_seconds

    job = repos.get_doc("processing_jobs", job_id)
    if not job:
        return "FAILED"
    s = get_settings()
    attempts = int(job.get("attempt_count", 0)) + 1
    max_attempts = int(job.get("max_attempts", 0) or s.JOB_MAX_ATTEMPTS)
    if retryable:
        # Bound each retry burst, then pause before trying again. A prolonged
        # network/API outage must not turn into a manual-resume requirement.
        exhausted = attempts >= max_attempts
        delay = s.JOB_RETRY_COOLDOWN_SECONDS if exhausted else backoff_delay_seconds(attempts)
        delay = max(delay, retry_after)
        repos.update_doc("processing_jobs", job_id, {
            "status": "QUEUED",
            "attempt_count": 0 if exhausted else attempts,
            "locked_by": "",
            "next_attempt_at": _iso(_now() + timedelta(seconds=delay)),
            "last_error": (error or "")[:2000],
        })
        return "QUEUED"
    else:
        repos.update_doc("processing_jobs", job_id, {
            "status": "FAILED",
            "attempt_count": attempts,
            "locked_by": "",
            "last_error": (error or "")[:2000],
        })
        return "FAILED"


def recover_stale_leases() -> int:
    """Return LEASED jobs with expired locks to QUEUED. Returns count recovered."""
    stale = repos.list_docs("processing_jobs", [
        Query.equal("status", "LEASED"),
        Query.less_than_equal("lock_expires_at", _iso(_now())),
        Query.limit(50),
    ], limit=50)
    n = 0
    for job in stale:
        try:
            repos.update_doc("processing_jobs", job["$id"], {"status": "QUEUED", "locked_by": ""})
            n += 1
        except Exception:
            continue
    return n


def backlog_count() -> int:
    from app.appwrite import repos

    return repos.count_docs("processing_jobs", [Query.equal("status", "QUEUED")])
