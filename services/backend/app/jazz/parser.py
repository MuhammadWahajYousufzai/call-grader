"""Jazz row dataclass + parser from HTML tables.

Pure functions so CI can test with fixtures without live credentials.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from dateutil import parser as dateparser

from app.jazz import selectors as sel


@dataclass
class JazzRow:
    row_id: str = ""
    timestamp_raw: str = ""
    started_at: datetime | None = None
    direction_raw: str = ""
    caller: str = ""
    callee: str = ""
    agent_identifier: str = ""
    duration_seconds: int = 0
    status_raw: str = ""
    recording_url: str = ""
    has_recording: bool = False
    extra: dict = field(default_factory=dict)


def parse_duration(raw: str) -> int:
    raw = (raw or "").strip()
    if not raw:
        return 0
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", raw)
    if m:
        parts = [int(p) for p in m.groups() if p is not None]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return 0


def parse_started_at(raw: str):
    if not raw or not raw.strip():
        return None
    try:
        from zoneinfo import ZoneInfo

        return datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=ZoneInfo("Asia/Karachi")
        )
    except Exception:
        try:
            parsed = dateparser.parse(raw.strip(), dayfirst=True)
            return parsed.replace(tzinfo=ZoneInfo("Asia/Karachi")) if parsed and not parsed.tzinfo else parsed
        except Exception:
            return None


def header_to_field(header: str) -> str | None:
    h = re.sub(r"\s+", " ", header.strip().lower())
    for field_name, hints in sel.COLUMN_HINTS.items():
        if any(hint in h for hint in hints):
            return field_name
    return None


def rows_from_dicts(headers: list[str], rows: list[list[str]]) -> list[JazzRow]:
    """Convert header + matrix (from Playwright table scrape) to JazzRow list."""
    fields = [header_to_field(h) for h in headers]
    out: list[JazzRow] = []
    for cells in rows:
        data: dict[str, str] = {}
        for f, c in zip(fields, cells):
            if f:
                data[f] = c.strip()
        direction = data.get("direction", "").strip().lower()
        client = data.get("client", "")
        ext = data.get("agent", "")
        caller = data.get("caller", "") or (client if direction == "inbound" else ext)
        callee = data.get("callee", "") or (ext if direction == "inbound" else client)
        jr = JazzRow(
            row_id=data.get("source_call_id", ""),
            timestamp_raw=data.get("timestamp", ""),
            started_at=parse_started_at(data.get("timestamp", "")),
            direction_raw=data.get("direction", ""),
            caller=caller,
            callee=callee,
            agent_identifier=ext,
            duration_seconds=parse_duration(data.get("duration", "")),
            status_raw=data.get("status", ""),
            recording_url=data.get("recording", ""),
            has_recording=bool(data.get("recording", "").strip()),
            extra={"bill_seconds": parse_duration(data.get("bill_seconds", "")), "client": client},
        )
        out.append(jr)
    return out


def extract_table_matrix(table_html: str) -> tuple[list[str], list[list[str]]]:
    """Fixture-friendly HTML parser for tests (no browser needed)."""
    from html.parser import HTMLParser

    class T(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_th = self.in_td = False
            self.in_thead = False
            self.headers: list[str] = []
            self.current: list[str] = []
            self.rows: list[list[str]] = []
            self.buf = ""

        def handle_starttag(self, tag, attrs):
            if tag == "thead":
                self.in_thead = True
            elif tag == "th":
                self.in_th = True
                self.buf = ""
            elif tag == "td":
                self.in_td = True
                self.buf = ""

        def handle_endtag(self, tag):
            if tag == "th":
                self.in_th = False
                if self.in_thead:
                    self.headers.append(self.buf.strip())
            elif tag == "thead":
                self.in_thead = False
            elif tag == "td":
                self.in_td = False
                self.current.append(self.buf.strip())
            elif tag == "tr":
                if self.current:
                    self.rows.append(self.current)
                    self.current = []

        def handle_data(self, data):
            if self.in_th or self.in_td:
                self.buf += data

    p = T()
    p.feed(table_html)
    return p.headers, p.rows
