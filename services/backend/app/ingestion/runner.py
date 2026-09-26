"""Ingestion runner: discovery -> checkpointed per-call persistence -> job enqueue.

Crash-safe: every call row is independently checkpointed in Appwrite before
moving on; resume logic never restarts a whole day.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from appwrite.query import Query

from app.appwrite import repos
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.domain.helpers import (
    dedupe_key,
    latest_processing_date,
    normalize_customer_number,
    normalize_status,
    reporting_date_for,
)

log = get_logger("ingestion")
PKT = ZoneInfo("Asia/Karachi")


def _direction(raw: str, caller: str, callee: str) -> str:
    s = (raw or "").lower()
    if any(k in s for k in ("out", "outgoing", "terminat", "o/b", "mobile originated")):
        return "OUTBOUND"
    if any(k in s for k in ("in", "incoming", "inbound", "originat", "i/b")):
        return "INBOUND"
    return "UNKNOWN"


def _customer(direction: str, caller: str, callee: str) -> tuple[str, str]:
    raw = caller if direction == "INBOUND" else (callee or caller)
    if direction == "UNKNOWN":
        raw = caller or callee
    return raw, normalize_customer_number(raw)


def row_to_call_doc(row, reporting_fallback: str = "") -> dict:
    started = row.started_at
    if started is None:
        raise ValueError("Jazz row has no parseable source timestamp")
    if started.tzinfo is None:
        started = started.replace(tzinfo=PKT)
    direction = _direction(row.direction_raw, row.caller, row.callee)
    raw_cust, norm_cust = _customer(direction, row.caller, row.callee)
    canon = normalize_status(row.status_raw).value
    rd = reporting_date_for(started).isoformat()
    dk = dedupe_key(
        started_at_iso=started.isoformat(),
        direction=direction,
        customer_number=raw_cust,
        agent_identifier=row.agent_identifier,
        duration_seconds=row.duration_seconds,
        row_id=row.row_id,
    )
    agent = repos.find_agent_by_jazz(row.agent_identifier)
    return {
        "source": "jazz_business_line",
        "source_call_id": row.row_id,
        "dedupe_key": dk,
        "actual_started_at": started.astimezone(UTC).isoformat(),
        "reporting_date": rd,
        "direction": direction,
        "raw_jazz_status": row.status_raw,
        "canonical_status": canon,
        "caller_number": row.caller,
        "callee_number": row.callee,
        "raw_customer_number": raw_cust,
        "normalized_customer_number": norm_cust,
        "agent_id": agent.get("$id", "") if agent else "",
        "agent_name_snapshot": agent.get("name", "") if agent else "Unassigned",
        "jazz_agent_identifier": row.agent_identifier,
        "duration_seconds": row.duration_seconds,
        "recording_available": bool(row.has_recording),
        "recording_storage_file_id": "",
        "recording_sha256": "",
        "pipeline_status": "METADATA_SAVED",
        "retry_count": 0,
        "last_error_code": "",
        "last_error_message": "",
        "raw_jazz_row": json.dumps({"ts": row.timestamp_raw, "url": row.recording_url})[:4000],
    }


def persist_rows(rows: list, run_id: str) -> dict:
    discovered = skipped = queued = 0
    for row in rows:
        doc = row_to_call_doc(row)
        existing, created = repos.upsert_call(doc) if hasattr(repos, "upsert_call") else (None, True)
        if not created:
            skipped += 1
            continue
        discovered += 1
        call_id = existing.get("$id", "") if isinstance(existing, dict) else ""
        # eligible for download only when answered-ish or recording present
        canon = doc["canonical_status"]
        if doc["recording_available"] and canon == "ANSWERED":
            repos.update_call(call_id, {"pipeline_status": "DOWNLOAD_PENDING"})
            repos.ensure_job("DOWNLOAD", call_id, doc["reporting_date"])
            queued += 1
        elif canon in ("NO_ANSWER", "BUSY"):
            repos.update_call(call_id, {"pipeline_status": "NOT_ELIGIBLE"})
        elif not doc["recording_available"] and canon == "ANSWERED":
            repos.update_call(call_id, {"pipeline_status": "NO_RECORDING"})
        else:
            repos.update_call(call_id, {"pipeline_status": "NOT_ELIGIBLE" if not doc["recording_available"] else "DOWNLOAD_PENDING"})
            if doc["recording_available"]:
                repos.ensure_job("DOWNLOAD", call_id, doc["reporting_date"])
                queued += 1
    return {"discovered": discovered, "skipped": skipped, "queued": queued}


def newest_jazz_call() -> dict | None:
    rows = repos.list_docs("calls", [Query.equal("source", "jazz_business_line"),
                                     Query.order_desc("actual_started_at")], limit=1)
    return rows[0] if rows else None


def discovery_dates(now: datetime | None = None) -> list[str]:
    """First run starts at Karachi midnight; later runs overlap the source cursor."""
    local_now = (now or datetime.now(PKT)).astimezone(PKT)
    latest = newest_jazz_call()
    if not latest:
        return [local_now.date().isoformat()]
    source_time = datetime.fromisoformat(latest["actual_started_at"].replace("Z", "+00:00"))
    start = (source_time.astimezone(PKT) - timedelta(minutes=get_settings().JAZZ_SYNC_OVERLAP_MINUTES)).date()
    if start > local_now.date():
        start = local_now.date()
    return [(start + timedelta(days=i)).isoformat()
            for i in range((local_now.date() - start).days + 1)]


def sync_window() -> list[dict]:
    """Automatic startup/scheduled sync based solely on persisted Jazz calls."""
    return [sync_date(d) for d in discovery_dates()]


def scheduled_sync_window(now: datetime | None = None) -> list[dict]:
    """Release one closed office-day batch; morning startup only catches up missed days."""
    local_now = (now or datetime.now(PKT)).astimezone(PKT)
    due = latest_processing_date(local_now)
    due_str = due.isoformat()
    if repos.get_setting("last_scheduled_reporting_date") >= due_str:
        return []
    latest = newest_jazz_call()
    if not latest and due < local_now.date():
        return []  # First-ever morning startup waits for today's 18:01 release.
    dates = discovery_dates(datetime.combine(due, time(18, 1), PKT))
    added_prior = ""
    if latest:
        # Yesterday's post-18:00 calls belong to this batch even if today's
        # source cursor already exists from a previous administrative sync.
        prior = (due - timedelta(days=1)).isoformat()
        if dates[0] > prior:
            dates.insert(0, prior)
            added_prior = prior
    results = [sync_date(d, max_reporting_date=due_str,
                         min_reporting_date=due_str if d == added_prior else None) for d in dates]
    if results and all(r.get("status") == "SUCCESS" for r in results):
        repos.set_setting("last_scheduled_reporting_date", due_str)
    return results


def refresh_reports(reporting_dates: set[str]) -> None:
    from app.reporting.compute import compute_report

    for rd in reporting_dates:
        calls = []
        offset = 0
        while True:
            batch = repos.list_docs("calls", [Query.equal("reporting_date", rd)], limit=100, offset=offset)
            calls.extend(batch)
            if len(batch) < 100:
                break
            offset += len(batch)
        grades = {}
        for call in calls:
            grade = repos.get_grade(call["$id"])
            if grade:
                try:
                    grades[call["$id"]] = json.loads(grade.get("result_json", "{}") or "{}")
                except Exception:
                    pass
        metrics = compute_report(calls, grades, threshold=get_settings().LOW_SCORE_THRESHOLD)
        status = "COMPLETE_WITH_ERRORS" if metrics.get("processing_failures", 0) else (
            "PROCESSING" if metrics.get("still_processing", 0) else "COMPLETE")
        repos.save_report(rd, status, metrics)


def acquire_sync_lock(lock_name: str = "jazz_sync", ttl_seconds: int = 1800) -> bool:
    """App-level ingestion lock via app_settings. Returns True if acquired."""
    from datetime import datetime
    now = datetime.now(UTC)
    val = repos.get_setting(f"lock_{lock_name}")
    if val:
        try:
            exp = datetime.fromisoformat(val)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=UTC)
            if exp > now:
                return False
        except Exception:
            pass
    repos.set_setting(f"lock_{lock_name}", (now + timedelta(seconds=ttl_seconds)).isoformat())
    return True


def release_sync_lock(lock_name: str = "jazz_sync") -> None:
    repos.set_setting(f"lock_{lock_name}", "")


def sync_date(date_str: str, run_id: str | None = None, max_reporting_date: str | None = None,
              min_reporting_date: str | None = None) -> dict:
    """Full sync for one date using the deterministic Playwright client."""
    from app.jazz.client import JazzClient

    run_id = run_id or uuid.uuid4().hex[:8]
    if not acquire_sync_lock():
        return {"status": "SKIPPED_LOCKED", "run_id": run_id}
    run_doc = repos.create_doc("ingestion_runs", {
        "started_at": datetime.now(UTC).isoformat(),
        "status": "RUNNING",
        "window_start": datetime.combine(date.fromisoformat(date_str), time.min, PKT).astimezone(UTC).isoformat(),
        "window_end": datetime.combine(date.fromisoformat(date_str), time.max, PKT).astimezone(UTC).isoformat(),
        "calls_discovered": 0,
        "recordings_downloaded": 0,
    })
    try:
        with JazzClient(state_dir=str(Path(get_settings().PLAYWRIGHT_STATE_DIR) / "sync")) as client:
            page = client.ensure_auth(run_id)
            mappings = client.extension_mappings(page)
            for agent in repos.list_agents():
                match = mappings.get(agent.get("name", "").strip().lower())
                if match and (agent.get("jazz_identifier"), agent.get("jazz_extension")) != match:
                    repos.update_doc("agents", agent["$id"], {
                        "jazz_identifier": match[0], "jazz_extension": match[1],
                    })
            rows = client.iter_call_rows(page, date_str, run_id)
        if max_reporting_date:
            rows = [row for row in rows
                    if reporting_date_for(row.started_at).isoformat() <= max_reporting_date]
        if min_reporting_date:
            rows = [row for row in rows
                    if reporting_date_for(row.started_at).isoformat() >= min_reporting_date]
        stats = persist_rows(rows, run_id)
        refresh_reports({date_str} | {reporting_date_for(row.started_at).isoformat() for row in rows})
        repos.set_setting("last_successful_sync", datetime.now(UTC).isoformat())
        repos.update_doc("ingestion_runs", run_doc["$id"], {
            "finished_at": datetime.now(UTC).isoformat(),
            "status": "SUCCESS",
            "calls_discovered": stats["discovered"],
        })
        return {"status": "SUCCESS", **stats, "run_id": run_id}
    except Exception as e:
        code = getattr(e, "code", "UNKNOWN")
        repos.update_doc("ingestion_runs", run_doc["$id"], {
            "finished_at": datetime.now(UTC).isoformat(),
            "status": "FAILED",
            "error_code": code,
            "error_message": str(e)[:2000],
        })
        return {"status": "FAILED", "error_code": code, "error": str(e)[:500], "run_id": run_id}
    finally:
        release_sync_lock()
