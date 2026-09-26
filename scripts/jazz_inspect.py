"""Optional, autonomous Jazz diagnostic. Never prints credentials or call numbers."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "backend"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headed", action="store_true", help="Show browser while diagnosing")
    ap.add_argument("--date", default=datetime.now(ZoneInfo("Asia/Karachi")).date().isoformat())
    ap.add_argument("--snapshot", default="", help="Optional path for sanitized CDR table HTML")
    args = ap.parse_args()

    from app.config.settings import get_settings
    from app.jazz.client import JazzClient
    from app.jazz.parser import extract_table_matrix

    s = get_settings()
    with JazzClient(state_dir=str(Path(s.PLAYWRIGHT_STATE_DIR) / "inspect"),
                    headed=args.headed) as client:
        page = client.ensure_auth("inspect")
        mappings = client.extension_mappings(page)
        rows = client.iter_call_rows(page, args.date, "inspect")
        print("authenticated:", client.is_authenticated(page))
        print("date:", args.date)
        for direction in ("OUTBOUND", "INBOUND"):
            headers, _ = extract_table_matrix(client._dated_table(page, direction, args.date))
            print(direction.lower(), "headers:", headers)
        print("rows:", len(rows), "directions:", dict(Counter(r.direction_raw for r in rows)))
        print("statuses:", dict(Counter(r.status_raw for r in rows)))
        print("recording detail controls:", sum(bool(r.recording_url) for r in rows))
        print("exact agent names:", sorted(mappings))
        print("pagination: Jazz AJAX returns all dated rows; DataTables paginates client-side")
        print("sanitized row fields:", ["timestamp", "extension", "client", "duration",
                                         "bill_seconds", "status", "direction", "recording_detail_id"])
        if args.snapshot:
            fragment = client._dated_table(page, "OUTBOUND", args.date)
            fragment = re.sub(r"\b\d{7,}\b", "[number]", fragment)
            fragment = re.sub(r"/callrecording/[^\"'\s<]+", "/callrecording/[id]", fragment)
            Path(args.snapshot).write_text(fragment)
            print("sanitized snapshot saved:", args.snapshot)


if __name__ == "__main__":
    main()
