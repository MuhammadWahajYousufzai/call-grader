"""Jazz portal models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class JazzCall:
    source_call_id: str
    started_at_iso: str
    direction: str  # INBOUND/OUTBOUND/UNKNOWN
    caller_number: str
    callee_number: str
    customer_number: str
    agent_identifier: str
    duration_seconds: int
    status_raw: str
    has_recording: bool
    row_id: str = ""
