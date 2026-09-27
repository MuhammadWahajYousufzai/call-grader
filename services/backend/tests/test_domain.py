import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.domain.helpers import (
    backoff_delay_seconds,
    dedupe_key,
    normalize_customer_number,
    normalize_status,
    reporting_date_for,
    retention_due,
    weighted_score,
)
from app.domain.states import RESUME_FROM
from app.jazz.parser import extract_table_matrix, parse_duration, rows_from_dicts
from app.reporting.compute import compute_report


def test_status_normalization():
    assert normalize_status("Answered") == "ANSWERED"
    assert normalize_status("No Answer") == "NO_ANSWER"
    assert normalize_status("Busy") == "BUSY"
    assert normalize_status("Failed") == "FAILED"
    assert normalize_status("Cancelled") == "CANCELLED"
    assert normalize_status("weird-new-status") == "UNKNOWN"


def test_outbound_reconciliation():
    calls = [
        {"direction": "OUTBOUND", "canonical_status": s, "$id": str(i),
         "agent_name_snapshot": "Saima", "pipeline_status": "COMPLETE",
         "recording_storage_file_id": "x"}
        for i, s in enumerate(["ANSWERED", "NO_ANSWER", "BUSY", "FAILED", "CANCELLED", "MYSTERY"])
    ]
    m = compute_report(calls, {})
    assert m["outbound"]["total"] == 6
    assert (m["outbound"]["ANSWERED"] + m["outbound"]["NO_ANSWER"] + m["outbound"]["BUSY"]
            + m["outbound"]["FAILED"] + m["outbound"]["CANCELLED"] + m["outbound"]["UNKNOWN"]
            + m["outbound"]["OTHER"]) == 6


def test_weighted_score_null_dims():
    dims = {"listening_and_understanding": 8.0, "order_accuracy": None,
            "communication_professionalism": 6.0, "product_policy_accuracy": None,
            "problem_solving": 7.0, "negotiation_objection_handling": None,
            "intent_handling": 9.0, "closing_follow_up": 5.0}
    score = weighted_score(dims)
    # manual: weights .2+.15+.15+.1+.05=.65; (1.6+.9+1.05+.9+.25)/.65
    assert 6.0 < score < 8.0
    with pytest.raises(ValueError):
        weighted_score({k: None for k in dims})


def test_dedupe_stable():
    k1 = dedupe_key(started_at_iso="2026-01-01T10:00:00+05:00", direction="OUTBOUND",
                    customer_number="+92 300 1234567", agent_identifier="SIP/101",
                    duration_seconds=120, row_id="abc")
    k2 = dedupe_key(started_at_iso="2026-01-01T10:00:00+05:00", direction="outbound",
                    customer_number="03001234567", agent_identifier="sip/101",
                    duration_seconds=120, row_id="abc")
    assert k1 == k2
    k3 = dedupe_key(started_at_iso="2026-01-01T10:01:00+05:00", direction="OUTBOUND",
                    customer_number="03001234567", agent_identifier="sip/101",
                    duration_seconds=120, row_id="abc")
    assert k1 != k3


def test_phone_normalization_keeps_raw():
    assert normalize_customer_number("03001234567") != ""
    assert normalize_customer_number("+923001234567") != ""


def test_reporting_dates():
    from datetime import date

    pkt = ZoneInfo("Asia/Karachi")
    assert reporting_date_for(datetime(2026, 1, 5, 17, 0, tzinfo=pkt)) == date(2026, 1, 5)
    # after 18:00 -> next day
    assert reporting_date_for(datetime(2026, 1, 5, 19, 30, tzinfo=pkt)) == date(2026, 1, 6)


def test_retention_15_days():

    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert retention_due(base, 15) == base + timedelta(days=15)


def test_backoff_bounded():
    for a in range(1, 8):
        assert 0 < backoff_delay_seconds(a) <= 400


def test_resume_map_crash_safety():
    assert RESUME_FROM["GRADING"] == "GRADING_PENDING"
    assert RESUME_FROM["DOWNLOADING"] == "DOWNLOAD_PENDING"
    assert RESUME_FROM["TRANSCRIBING"] == "TRANSCRIPTION_PENDING"


def test_jazz_parser_fixture():
    html = """<table><thead><tr><th>Date/Time</th><th>Direction</th><th>Caller</th>
    <th>Callee</th><th>Extension</th><th>Duration</th><th>Status</th></tr></thead>
    <tbody><tr><td>05/01/2026 10:00</td><td>Outgoing</td><td>0213456789</td>
    <td>03001234567</td><td>SIP/101</td><td>02:30</td><td>Answered</td></tr></tbody></table>"""
    headers, rows = extract_table_matrix(html)
    parsed = rows_from_dicts(headers, rows)
    assert len(parsed) == 1
    assert parsed[0].duration_seconds == 150
    assert parsed[0].caller == "0213456789"


def test_parse_duration_variants():
    assert parse_duration("150") == 150
    assert parse_duration("02:30") == 150
    assert parse_duration("1:02:30") == 3750
