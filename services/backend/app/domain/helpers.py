"""Deterministic helpers: dedupe key, phone normalization, reporting date, scoring."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .states import CanonicalStatus

APP_TZ = ZoneInfo("Asia/Karachi")


def latest_processing_date(now: datetime | None = None) -> date:
    """Only closed office-day batches are eligible; daily release is 18:01 PKT."""
    local = (now or datetime.now(APP_TZ)).astimezone(APP_TZ)
    return local.date() if local.time() >= time(18, 1) else local.date() - timedelta(days=1)


def normalize_status(raw: str) -> CanonicalStatus:
    s = (raw or "").strip().lower()
    if not s:
        return CanonicalStatus.UNKNOWN
    no_answer = ("no answer", "no-answer", "noanswer", "missed", "unanswered", "not answered", "no response")
    busy = ("busy", "engaged")
    answered = ("answer", "connected", "completed", "success", "talk", "conversation")
    failed = ("fail", "error", "congestion", "unreachable", "invalid")
    cancelled = ("cancel", "abort", "rejected", "declined")
    if any(k in s for k in no_answer):
        return CanonicalStatus.NO_ANSWER
    if any(k in s for k in busy):
        return CanonicalStatus.BUSY
    if any(k in s for k in cancelled):
        return CanonicalStatus.CANCELLED
    if any(k in s for k in failed):
        return CanonicalStatus.FAILED
    if any(k in s for k in answered):
        return CanonicalStatus.ANSWERED
    return CanonicalStatus.UNKNOWN


def normalize_customer_number(raw: str) -> str:
    """Normalize Pakistani numbers to 0XXX-XXXXXXX style digits (keep raw separately)."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    # +92... -> 0...
    if digits.startswith("92") and len(digits) >= 12:
        digits = "0" + digits[2:]
    elif digits.startswith("0092"):
        digits = "0" + digits[4:]
    try:
        import phonenumbers

        num = phonenumbers.parse("+" + digits if digits.startswith("92") else digits, "PK")
        if phonenumbers.is_possible_number(num):
            return phonenumbers.format_in_original_format(num, "PK") if False else re.sub(
                r"\D", "", phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164)
            )
    except Exception:
        pass
    return digits


def dedupe_key(
    *,
    started_at_iso: str,
    direction: str,
    customer_number: str,
    agent_identifier: str,
    duration_seconds: int,
    row_id: str = "",
) -> str:
    # Jazz reuses one recording ID for multiple inbound routing legs. Keep the
    # source ID in the fingerprint, but include row-level metadata as well.
    ts = started_at_iso.strip()
    cust = normalize_customer_number(customer_number or "")
    agent = (agent_identifier or "").strip().lower()
    payload = "|".join([
        ts,
        (direction or "").upper(),
        cust,
        agent,
        str(int(duration_seconds or 0)),
        (row_id or "").strip(),
    ])
    return hashlib.sha256(payload.encode()).hexdigest()


def reporting_date_for(
    actual: datetime,
    day_end: time = time(18, 0),
    tz: ZoneInfo = APP_TZ,
) -> date:
    """Through 18:00 -> current date; after 18:00 -> next date. Aware datetimes respected."""
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=tz)
    local = actual.astimezone(tz)
    cutoff = datetime.combine(local.date(), day_end, tzinfo=tz)
    if local.time() > day_end:
        return local.date() + timedelta(days=1)
    if local > cutoff:
        return local.date() + timedelta(days=1)
    return local.date()


RUBRIC_WEIGHTS: dict[str, float] = {
    "listening_and_understanding": 0.20,
    "communication_professionalism": 0.15,
    "product_policy_accuracy": 0.15,
    "problem_solving": 0.15,
    "negotiation_objection_handling": 0.15,
    "intent_handling": 0.10,
    "order_accuracy": 0.05,
    "closing_follow_up": 0.05,
}


def weighted_score(dimensions: dict[str, float | None]) -> float:
    """Deterministic weighted score; null dims excluded and weights renormalized. Never invented by LLM."""
    applicable = {k: v for k, v in dimensions.items() if v is not None and k in RUBRIC_WEIGHTS}
    if not applicable:
        raise ValueError("No applicable dimensions to score")
    total_w = sum(RUBRIC_WEIGHTS[k] for k in applicable)
    raw = sum(float(v) * RUBRIC_WEIGHTS[k] for k, v in applicable.items()) / total_w
    return round(max(1.0, min(10.0, raw)), 1)


def retention_due(actual_call_at: datetime, days: int = 15) -> datetime:
    return actual_call_at + timedelta(days=days)


def backoff_delay_seconds(attempt: int, base: float = 2.0, cap: float = 300.0) -> float:
    import random

    exp = min(cap, base * (2 ** max(0, attempt - 1)))
    return round(exp + random.uniform(0, exp * 0.25), 2)
