"""Typed repository layer over Appwrite TablesDB + Storage.

All queries go through here so routes/workers never scatter SDK calls.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from appwrite.query import Query

from app.appwrite import client as aw


def _db() -> str:
    return aw.database_id()


DB = _db


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ---- generic helpers -------------------------------------------------------

def _flat(d: dict) -> dict:
    """TablesDB rows nest user columns under 'data' — flatten to top level."""
    data = d.get("data")
    if isinstance(data, dict):
        return {**data, **{k: v for k, v in d.items() if k != "data"}}
    return d


def _extract_rows(res: Any) -> tuple[list[dict], int]:
    if isinstance(res, dict):
        docs = res.get("rows", res.get("documents", []))
        total = int(res.get("total", len(docs)))
        return [_flat(d) if isinstance(d, dict) else {"raw": str(d)} for d in docs], total
    docs = getattr(res, "rows", getattr(res, "documents", [])) or []
    total = int(getattr(res, "total", len(docs)) or 0)
    out = []
    for d in docs:
        if isinstance(d, dict):
            out.append(_flat(d))
        elif hasattr(d, "to_dict"):
            try:
                out.append(_flat(d.to_dict()))
            except Exception:
                out.append({"raw": str(d)})
        else:
            out.append({"raw": str(d)})
    return out, total


def _as_dict(res: Any) -> dict:
    if isinstance(res, dict):
        return _flat(res)
    if hasattr(res, "to_dict"):
        try:
            return _flat(res.to_dict())
        except Exception:
            pass
    if hasattr(res, "__dict__"):
        return dict(res.__dict__)
    return {"raw": str(res)}


def list_docs(table: str, queries: list | None = None, limit: int = 100, offset: int = 0) -> list[dict]:
    q = list(queries or []) + [Query.limit(limit), Query.offset(offset)]
    res = aw.tables().list_rows(database_id=DB(), table_id=table, queries=q)
    rows, _ = _extract_rows(res)
    return rows


def count_docs(table: str, queries: list | None = None) -> int:
    res = aw.tables().list_rows(database_id=DB(), table_id=table,
                                queries=list(queries or []) + [Query.limit(1)])
    _, total = _extract_rows(res)
    return total


def get_doc(table: str, doc_id: str) -> dict | None:
    try:
        return _as_dict(aw.tables().get_row(database_id=DB(), table_id=table, row_id=doc_id))
    except Exception:
        return None


def create_doc(table: str, data: dict, doc_id: str | None = None) -> dict:
    from appwrite.id import ID

    return _as_dict(aw.tables().create_row(
        database_id=DB(), table_id=table, row_id=doc_id or ID.unique(), data=data))


def update_doc(table: str, doc_id: str, data: dict) -> dict:
    return _as_dict(aw.tables().update_row(
        database_id=DB(), table_id=table, row_id=doc_id, data=data))


def delete_doc(table: str, doc_id: str) -> None:
    aw.tables().delete_row(database_id=DB(), table_id=table, row_id=doc_id)


def find_by(table: str, field: str, value: Any, limit: int = 25) -> list[dict]:
    return list_docs(table, [Query.equal(field, value)], limit=limit)


# ---- domain repos ----------------------------------------------------------

def find_call_by_dedupe(dedupe_key: str) -> dict | None:
    rows = find_by("calls", "dedupe_key", dedupe_key, limit=2)
    return rows[0] if rows else None


def upsert_call(call: dict) -> tuple[dict, bool]:
    """Idempotent upsert by dedupe_key. Returns (doc, created)."""
    existing = find_call_by_dedupe(call["dedupe_key"])
    if existing:
        return existing, False
    try:
        doc = create_doc("calls", call)
        return doc, True
    except Exception:
        # A concurrent sync may have won the unique dedupe index race.
        existing = find_call_by_dedupe(call["dedupe_key"])
        if existing:
            return existing, False
        raise


def update_call(doc_id: str, patch: dict) -> dict:
    return update_doc("calls", doc_id, patch)


def find_agent_by_jazz(identifier: str) -> dict | None:
    if not identifier:
        return None
    rows = find_by("agents", "jazz_identifier", identifier, limit=2)
    if rows:
        return rows[0]
    rows = find_by("agents", "jazz_extension", identifier, limit=2)
    return rows[0] if rows else None


def list_agents() -> list[dict]:
    return list_docs("agents", limit=100)


def save_segments(call_id: str, segments: list[dict]) -> None:
    for s in segments:
        create_doc("transcript_segments", {"call_id": call_id, **s})


def get_segments(call_id: str) -> list[dict]:
    rows = []
    while True:
        queries = [Query.equal("call_id", call_id), Query.order_asc("sequence")]
        if rows:
            queries.append(Query.cursor_after(rows[-1]["$id"]))
        batch = list_docs("transcript_segments", queries, limit=100)
        rows.extend(batch)
        if len(batch) < 100:
            return rows


def save_grade(grade: dict) -> dict:
    existing = find_by("call_grades", "call_id", grade["call_id"], limit=2)
    if existing:
        return update_doc("call_grades", existing[0]["$id"], grade)
    return create_doc("call_grades", grade)


def get_grade(call_id: str) -> dict | None:
    rows = find_by("call_grades", "call_id", call_id, limit=2)
    return rows[0] if rows else None


def enqueue_job(job_type: str, call_id: str = "", reporting_date: str = "", max_attempts: int = 6) -> dict:
    return create_doc("processing_jobs", {
        "job_type": job_type,
        "call_id": call_id,
        "reporting_date": reporting_date,
        "status": "QUEUED",
        "attempt_count": 0,
        "max_attempts": max_attempts,
        "next_attempt_at": now_iso(),
        "locked_by": "",
        "lock_expires_at": "",
        "last_error": "",
    })


def ensure_job(job_type: str, call_id: str, reporting_date: str = "") -> dict:
    """Keep at most one live job for a call and phase across restarts."""
    rows = list_docs("processing_jobs", [Query.equal("call_id", call_id)], limit=100)
    for row in rows:
        if row.get("job_type") == job_type and row.get("status") in ("QUEUED", "LEASED"):
            return row
    return enqueue_job(job_type, call_id=call_id, reporting_date=reporting_date)


def ensure_report_job(reporting_date: str) -> dict:
    rows = list_docs("processing_jobs", [Query.equal("reporting_date", reporting_date)], limit=100)
    for row in rows:
        if row.get("job_type") == "REPORT" and row.get("status") in ("QUEUED", "LEASED"):
            return row
    return enqueue_job("REPORT", reporting_date=reporting_date)


def get_setting(key: str) -> str:
    rows = find_by("app_settings", "key", key, limit=2)
    return rows[0].get("value", "") if rows else ""


def set_setting(key: str, value: str) -> None:
    rows = find_by("app_settings", "key", key, limit=2)
    if rows:
        update_doc("app_settings", rows[0]["$id"], {"value": value})
    else:
        create_doc("app_settings", {"key": key, "value": value})


def audit(actor: str, action: str, target: str, metadata: dict | None = None) -> None:
    create_doc("audit_logs", {
        "actor": actor,
        "action": action,
        "target": target,
        "metadata": json.dumps(metadata or {})[:4000],
    })


def get_report(reporting_date: str) -> dict | None:
    rows = find_by("daily_reports", "reporting_date", reporting_date, limit=2)
    return rows[0] if rows else None


def save_report(reporting_date: str, status: str, metrics: dict, coaching_summary: str | None = None) -> dict:
    existing = get_report(reporting_date)
    payload = {
        "reporting_date": reporting_date,
        "status": status,
        "metrics_json": json.dumps(metrics)[:65000],
        "coaching_summary": ((existing or {}).get("coaching_summary", "")
                             if coaching_summary is None else coaching_summary)[:16000],
    }
    if existing:
        return update_doc("daily_reports", existing["$id"], payload)
    return create_doc("daily_reports", payload)
