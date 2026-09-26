"""Deterministic daily report aggregation. LLM never counts calls."""

from __future__ import annotations

from collections import Counter
from typing import Any


def compute_report(calls: list[dict], grades: dict[str, dict], threshold: float = 6.0) -> dict:
    outbound = [c for c in calls if c.get("direction") == "OUTBOUND"]
    inbound = [c for c in calls if c.get("direction") == "INBOUND"]

    def bucket(calls_list: list[dict]) -> dict[str, int]:
        b = Counter(c.get("canonical_status", "UNKNOWN") or "UNKNOWN" for c in calls_list)
        total = len(calls_list)
        assert total == sum(b.values()), "status buckets must reconcile to total"
        return {
            "total": total,
            "ANSWERED": b.get("ANSWERED", 0),
            "NO_ANSWER": b.get("NO_ANSWER", 0),
            "BUSY": b.get("BUSY", 0),
            "FAILED": b.get("FAILED", 0),
            "CANCELLED": b.get("CANCELLED", 0),
            "UNKNOWN": b.get("UNKNOWN", 0),
            "OTHER": sum(v for k, v in b.items() if k not in
                         ("ANSWERED", "NO_ANSWER", "BUSY", "FAILED", "CANCELLED", "UNKNOWN")),
        }

    out_b = bucket(outbound)
    assert out_b["total"] == out_b["ANSWERED"] + out_b["NO_ANSWER"] + out_b["BUSY"] + out_b["FAILED"] + out_b["CANCELLED"] + out_b["UNKNOWN"] + out_b["OTHER"]

    def answered_by(agent_name: str, pool: list[dict]) -> int:
        return sum(1 for c in pool if c.get("canonical_status") == "ANSWERED"
                   and (c.get("agent_name_snapshot", "") or "").lower() == agent_name.lower())

    agent_names = sorted({c.get("agent_name_snapshot", "") for c in calls if c.get("agent_name_snapshot")})
    answered_out_by = {a: answered_by(a, outbound) for a in agent_names}
    combined_by = {a: sum(1 for c in calls if c.get("canonical_status") == "ANSWERED"
                          and (c.get("agent_name_snapshot", "") or "") == a) for a in agent_names}
    combined_total = sum(1 for c in calls if c.get("canonical_status") == "ANSWERED")

    graded = [g for g in grades.values() if g]
    scores = [float(g.get("overall_score", 0)) for g in graded if g.get("overall_score")]
    avg = round(sum(scores) / len(scores), 2) if scores else 0.0

    def avg_for(agent: str) -> float:
        vals = [float(grades[c.get("$id", "")].get("overall_score", 0))
                for c in calls
                if (c.get("agent_name_snapshot", "") or "") == agent and c.get("$id", "") in grades
                and grades[c.get("$id", "")].get("overall_score")]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    low = sum(1 for g in graded if float(g.get("overall_score", 10) or 10) < threshold)
    complaints = sum(1 for g in graded if g.get("complaint_detected") or g.get("issue_detected"))
    resolved = sum(1 for g in graded if g.get("issue_resolved"))
    orders = sum(1 for g in graded if g.get("order_detected"))
    followups = sum(1 for g in graded if g.get("follow_up_required"))
    flags_hc = sum(len([f for f in (g.get("critical_flags") or []) if isinstance(f, dict) and f.get("severity") in ("high", "critical")]
                       if isinstance(g.get("critical_flags"), list) else 0) for g in graded)
    missing = sum(1 for c in calls if c.get("canonical_status") == "ANSWERED" and not c.get("recording_storage_file_id") and not c.get("recording_deleted_at"))
    failed = sum(1 for c in calls if (c.get("pipeline_status", "") or "").endswith("FAILED"))
    processing = sum(1 for c in calls if c.get("pipeline_status", "") not in
                     ("COMPLETE", "NO_RECORDING", "NO_SPEECH", "UNGRADABLE", "NOT_ELIGIBLE")
                     and "FAILED" not in c.get("pipeline_status", ""))

    metrics: dict[str, Any] = {
        "outbound": out_b,
        "inbound_total": len(inbound),
        "answered_outbound_by_agent": answered_out_by,
        "combined_answered_by_agent": combined_by,
        "combined_answered_total": combined_total,
        "calls_graded": len(graded),
        "average_score": avg,
        "average_by_agent": {a: avg_for(a) for a in agent_names},
        "low_score_calls": low,
        "complaints": complaints,
        "resolved_complaints": resolved,
        "unresolved_complaints": max(0, complaints - resolved),
        "orders_detected": orders,
        "follow_ups_required": followups,
        "high_critical_flags": flags_hc,
        "recordings_missing": missing,
        "no_speech_calls": sum(c.get("pipeline_status") == "NO_SPEECH" for c in calls),
        "ungradable_calls": sum(c.get("pipeline_status") == "UNGRADABLE" for c in calls),
        "processing_failures": failed,
        "still_processing": processing,
        "total_calls": len(calls),
    }
    return metrics
