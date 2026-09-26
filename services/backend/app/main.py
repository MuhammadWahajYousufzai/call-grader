"""FastAPI app: typed routes for dashboard/reporting/admin/system."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from appwrite.query import Query
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi import Query as FQuery
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.appwrite import client as aw
from app.appwrite import repos
from app.config.logging import get_logger, setup_logging
from app.config.settings import get_settings, validate_for_role
from app.reporting.compute import compute_report

setup_logging("api")
log = get_logger("api")

app = FastAPI(title="Yousuf Rice Call Grader API", version="1.0.0")


def require_internal(x_internal_token: str | None = Header(default=None)) -> str:
    s = get_settings()
    if not s.INTERNAL_API_TOKEN:
        raise HTTPException(status_code=503, detail="internal access is not configured")
    if x_internal_token != s.INTERNAL_API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid internal token")
    # actor identity forwarded by Next.js BFF after Appwrite session verification
    return x_internal_token or ""


@app.on_event("startup")
def _startup() -> None:
    missing = validate_for_role(get_settings(), "api")
    if missing:
        log.warning(f"missing config: {missing}")


@app.get("/health/live")
def live() -> dict:
    return {"ok": True, "ts": datetime.now(UTC).isoformat()}


@app.get("/health/ready")
def ready() -> dict:
    try:
        repos.list_docs("app_settings", limit=1)
        appwrite_ok = True
    except Exception as e:
        appwrite_ok = False
        detail = str(e)[:300]
        return {"ok": False, "appwrite": False, "detail": detail}
    return {"ok": True, "appwrite": appwrite_ok}


# ---- dashboard ----
@app.get("/api/dashboard")
def dashboard(reporting_date: str | None = None, authed: str = Depends(require_internal)) -> dict:
    s = get_settings()
    rd = reporting_date or datetime.now(ZoneInfo("Asia/Karachi")).date().isoformat()
    calls = repos.list_docs("calls", [Query.equal("reporting_date", rd)], limit=500)
    grades = {}
    for c in calls:
        g = repos.get_grade(c.get("$id", ""))
        if g:
            try:
                grades[c["$id"]] = json.loads(g.get("result_json", "{}") or "{}")
            except Exception:
                pass
    metrics = compute_report(calls, grades, threshold=s.LOW_SCORE_THRESHOLD)
    attention = [c for c in calls
                 if c.get("pipeline_status") == "UNGRADABLE"
                 or (grades.get(c.get("$id", ""), {}).get("overall_score", 10) or 10) < s.LOW_SCORE_THRESHOLD
                 or grades.get(c.get("$id", ""), {}).get("critical_flags")]
    latest_runs = repos.list_docs("ingestion_runs", [Query.order_desc("$createdAt")], limit=1)
    alert = "Jazz authentication needs attention" if latest_runs and latest_runs[0].get("error_code") == "JAZZ_AUTH_BLOCKED" else ""
    return {"reporting_date": rd, "metrics": metrics,
            "system_alert": alert,
            "attention": [{"$id": c.get("$id"), "customer": c.get("raw_customer_number"),
                           "agent": c.get("agent_name_snapshot"), "status": c.get("pipeline_status")} for c in attention[:25]]}


@app.get("/api/reports")
def reports_list(limit: int = 30, authed: str = Depends(require_internal)) -> dict:
    rows = repos.list_docs("daily_reports", [Query.order_desc("$createdAt")], limit=limit)
    return {"reports": rows}


@app.get("/api/reports/{reporting_date}")
def report_detail(reporting_date: str, authed: str = Depends(require_internal)) -> dict:
    rep = repos.get_report(reporting_date)
    calls = repos.list_docs("calls", [Query.equal("reporting_date", reporting_date)], limit=500)
    grades = {}
    for c in calls:
        g = repos.get_grade(c.get("$id", ""))
        if g:
            try:
                grades[c["$id"]] = json.loads(g.get("result_json", "{}") or "{}")
            except Exception:
                pass
    metrics = compute_report(calls, grades) if calls else (json.loads(rep["metrics_json"]) if rep else {})
    return {"report": rep, "metrics": metrics,
            "coaching_summary": (rep or {}).get("coaching_summary", "")}


@app.get("/api/calls")
def calls_list(
    reporting_date: str | None = None,
    agent: str | None = None,
    direction: str | None = None,
    status: str | None = None,
    customer: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    category: str | None = None,
    limit: int = FQuery(default=50, le=200),
    offset: int = 0,
    authed: str = Depends(require_internal),
) -> dict:
    from app.domain.helpers import normalize_customer_number

    q: list = []
    if reporting_date:
        q.append(Query.equal("reporting_date", reporting_date))
    if direction:
        q.append(Query.equal("direction", direction))
    if status:
        q.append(Query.equal("canonical_status", status))
    if customer:
        q.append(Query.equal("normalized_customer_number", normalize_customer_number(customer)))
    if agent:
        q.append(Query.equal("agent_name_snapshot", agent))
    rows = repos.list_docs("calls", q, limit=limit, offset=offset)
    # score/category filters applied post-fetch (grades live in sibling table)
    out = []
    for c in rows:
        g = repos.get_grade(c.get("$id", ""))
        score = None
        intent = ""
        if g:
            try:
                data = json.loads(g.get("result_json", "{}") or "{}")
                score = data.get("overall_score")
                intent = data.get("primary_intent", "")
            except Exception:
                pass
        if min_score is not None and (score is None or score < min_score):
            continue
        if max_score is not None and (score is None or score > max_score):
            continue
        if category and intent != category:
            continue
        out.append({k: c.get(k) for k in (
            "$id", "reporting_date", "actual_started_at", "direction", "canonical_status",
            "raw_customer_number", "agent_name_snapshot", "duration_seconds", "pipeline_status")} | {"score": score, "intent": intent})
    return {"calls": out, "limit": limit, "offset": offset}


@app.get("/api/calls/{call_id}")
def call_detail(call_id: str, authed: str = Depends(require_internal)) -> dict:
    c = repos.get_doc("calls", call_id)
    if not c:
        raise HTTPException(404, "call not found")
    segs = repos.get_segments(call_id)
    grade = repos.get_grade(call_id)
    data = None
    if grade:
        try:
            data = json.loads(grade.get("result_json", "{}") or "{}")
        except Exception:
            data = None
    audio = bool(c.get("recording_storage_file_id")) and not c.get("recording_deleted_at")
    return {"call": c, "segments": segs, "grade": grade, "grade_data": data,
            "audio_available": audio,
            "recording_expires_on": c.get("recording_retention_due_at", "")}


@app.get("/api/calls/{call_id}/audio")
def call_audio(call_id: str, authed: str = Depends(require_internal)):
    """Authenticated streaming proxy — no permanent public URL, 15-day expiry enforced."""
    c = repos.get_doc("calls", call_id)
    if not c or not c.get("recording_storage_file_id"):
        raise HTTPException(404, "recording unavailable (expired or missing)")
    data = aw.storage().get_file_download(bucket_id=aw.bucket_id(), file_id=c["recording_storage_file_id"])

    def gen():
        yield data if isinstance(data, (bytes, bytearray)) else bytes(data)

    return StreamingResponse(gen(), media_type="audio/mpeg")


@app.get("/api/customers/{number}/calls")
def customer_calls(number: str, authed: str = Depends(require_internal)) -> dict:
    from app.domain.helpers import normalize_customer_number

    norm = normalize_customer_number(number)
    rows = repos.list_docs("calls", [Query.equal("normalized_customer_number", norm)], limit=200)
    return {"customer": number, "normalized": norm, "calls": rows}


@app.get("/api/agents")
def agents_list(authed: str = Depends(require_internal)) -> dict:
    agents = repos.list_agents()
    out = []
    for a in agents:
        calls = repos.list_docs("calls", [Query.equal("agent_id", a.get("$id", ""))], limit=500)
        scores = []
        for c in calls:
            g = repos.get_grade(c.get("$id", ""))
            if g:
                try:
                    scores.append(float(json.loads(g.get("result_json", "{}") or "{}").get("overall_score", 0)))
                except Exception:
                    pass
        out.append({"agent": a, "total_answered": sum(1 for c in calls if c.get("canonical_status") == "ANSWERED"),
                    "avg_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
                    "calls_graded": len(scores)})
    return {"agents": out}


@app.get("/api/agents/{agent_id}")
def agent_detail(agent_id: str, authed: str = Depends(require_internal)) -> dict:
    a = repos.get_doc("agents", agent_id)
    if not a:
        raise HTTPException(404, "agent not found")
    calls = repos.list_docs("calls", [Query.equal("agent_id", agent_id)], limit=500)
    grades = {}
    for c in calls:
        g = repos.get_grade(c.get("$id", ""))
        if g:
            try:
                grades[c["$id"]] = json.loads(g.get("result_json", "{}") or "{}")
            except Exception:
                pass
    metrics = compute_report(calls, grades) if calls else {}
    recent = sorted(calls, key=lambda c: c.get("actual_started_at", ""), reverse=True)[:20]
    return {"agent": a, "metrics": metrics, "recent_calls": recent}


class AgentMapIn(BaseModel):
    name: str
    jazz_identifier: str = ""
    jazz_extension: str = ""
    active: bool = True


@app.post("/api/admin/agents")
def upsert_agent(body: AgentMapIn, x_actor: str | None = Header(default="admin"), authed: str = Depends(require_internal)) -> dict:
    existing = repos.find_agent_by_jazz(body.jazz_identifier) if body.jazz_identifier else None
    if existing:
        doc = repos.update_doc("agents", existing["$id"], body.model_dump())
    else:
        doc = repos.create_doc("agents", body.model_dump())
    repos.audit(x_actor or "admin", "agent_mapping_change", doc.get("$id", ""), body.model_dump())
    return {"agent": doc}


class RuleIn(BaseModel):
    key: str
    value: str


@app.get("/api/admin/rules")
def rules_list(authed: str = Depends(require_internal)) -> dict:
    return {"rules": repos.list_docs("business_rules", limit=50)}


@app.post("/api/admin/rules")
def rule_upsert(body: RuleIn, x_actor: str | None = Header(default="admin"), authed: str = Depends(require_internal)) -> dict:
    rows = repos.find_by("business_rules", "key", body.key, limit=2)
    if rows:
        doc = repos.update_doc("business_rules", rows[0]["$id"], {"value": body.value,
                                                                   "version": int(rows[0].get("version", 1) or 1) + 1})
    else:
        doc = repos.create_doc("business_rules", {"key": body.key, "value": body.value, "version": 1})
    repos.audit(x_actor or "admin", "business_rule_change", body.key, {"key": body.key})
    return {"rule": doc}


class ReviewIn(BaseModel):
    human_score: float | None = None
    accurate: bool | None = None
    note: str = ""
    reviewer: str = "owner"


@app.post("/api/calls/{call_id}/review")
def human_review(call_id: str, body: ReviewIn, x_actor: str | None = Header(default="owner"), authed: str = Depends(require_internal)) -> dict:
    g = repos.get_grade(call_id)
    if not g:
        raise HTTPException(404, "grade not found")
    patch = {"human_reviewed": True, "human_review_notes": body.note[:4000],
             "reviewed_by": body.reviewer, "reviewed_at": datetime.now(UTC).isoformat()}
    if body.human_score is not None:
        patch["human_score"] = body.human_score
    doc = repos.update_doc("call_grades", g["$id"], patch)
    repos.audit(x_actor or "owner", "human_review", call_id, {"score": body.human_score, "accurate": body.accurate})
    return {"grade": doc}


# ---- admin controls (audit logged) ----
def _audit_admin(actor: str | None, action: str, target: str) -> None:
    repos.audit(actor or "admin", action, target, {})


@app.post("/api/admin/jazz/sync")
def admin_sync(date: str | None = None, x_actor: str | None = Header(default="admin"), authed: str = Depends(require_internal)) -> dict:
    from app.ingestion.runner import sync_date, sync_window

    _audit_admin(x_actor, "manual_jazz_sync", date or "auto")
    return sync_date(date) if date else {"runs": sync_window()}


@app.post("/api/admin/jobs/{job_id}/retry")
def admin_retry(job_id: str, x_actor: str | None = Header(default="admin"), authed: str = Depends(require_internal)) -> dict:
    job = repos.get_doc("processing_jobs", job_id)
    if not job:
        raise HTTPException(404, "job not found")
    repos.update_doc("processing_jobs", job_id, {"status": "QUEUED", "locked_by": "",
                                                 "next_attempt_at": datetime.now(UTC).isoformat()})
    _audit_admin(x_actor, "manual_retry", job_id)
    return {"ok": True}


@app.post("/api/admin/calls/{call_id}/retranscribe")
def admin_retranscribe(call_id: str, x_actor: str | None = Header(default="admin"), authed: str = Depends(require_internal)) -> dict:
    repos.enqueue_job("TRANSCRIBE", call_id=call_id)
    repos.update_call(call_id, {"pipeline_status": "TRANSCRIPTION_PENDING"})
    _audit_admin(x_actor, "manual_retranscribe", call_id)
    return {"ok": True}


@app.post("/api/admin/calls/{call_id}/regrade")
def admin_regrade(call_id: str, x_actor: str | None = Header(default="admin"), authed: str = Depends(require_internal)) -> dict:
    c = repos.get_doc("calls", call_id)
    repos.enqueue_job("GRADE", call_id=call_id, reporting_date=(c or {}).get("reporting_date", ""))
    if c:
        repos.update_call(call_id, {"pipeline_status": "GRADING_PENDING"})
    _audit_admin(x_actor, "manual_regrade", call_id)
    return {"ok": True}


@app.post("/api/admin/reports/{reporting_date}/regenerate")
def admin_regen(reporting_date: str, x_actor: str | None = Header(default="admin"), authed: str = Depends(require_internal)) -> dict:
    from app.ai.workflows import daily_coaching_summary

    s = get_settings()
    calls = repos.list_docs("calls", [Query.equal("reporting_date", reporting_date)], limit=500)
    grades = {}
    for c in calls:
        g = repos.get_grade(c.get("$id", ""))
        if g:
            try:
                grades[c["$id"]] = json.loads(g.get("result_json", "{}") or "{}")
            except Exception:
                pass
    metrics = compute_report(calls, grades, threshold=s.LOW_SCORE_THRESHOLD)
    status = "COMPLETE" if metrics.get("still_processing", 0) == 0 and metrics.get("processing_failures", 0) == 0 else (
        "COMPLETE_WITH_ERRORS" if metrics.get("processing_failures", 0) else "PROCESSING")
    coaching = ""
    try:
        coaching = daily_coaching_summary(metrics, list(grades.values())[:10])
    except Exception:
        pass
    doc = repos.save_report(reporting_date, status, metrics, coaching)
    _audit_admin(x_actor, "regenerate_report", reporting_date)
    return {"report": doc, "metrics": metrics}


@app.get("/api/system/status")
def system_status(authed: str = Depends(require_internal)) -> dict:
    from app.jobs.queue import backlog_count

    runs = repos.list_docs("ingestion_runs", [Query.order_desc("$createdAt")], limit=5)
    failed_jobs = repos.list_docs("processing_jobs", [Query.equal("status", "FAILED")], limit=25)
    reports = repos.list_docs("daily_reports", [Query.order_desc("$createdAt")], limit=3)
    return {
        "last_sync": repos.get_setting("last_successful_sync"),
        "last_login": repos.get_setting("last_successful_login"),
        "next_scheduled_sync": "18:01 Asia/Karachi daily",
        "recent_runs": runs,
        "backlog": backlog_count(),
        "failed_jobs": failed_jobs,
        "recent_reports": reports,
    }
