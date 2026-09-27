"""Authenticated Jazz Business Line adapter using verified portal endpoints."""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import BrowserContext, Page, sync_playwright

from app.config.settings import get_settings, require_jazz
from app.jazz import selectors as sel
from app.jazz.exceptions import (
    JazzAuthFailed,
    JazzBlocked,
    JazzDownloadFailed,
    JazzPageChanged,
    JazzTimeout,
)
from app.jazz.parser import JazzRow, parse_duration, rows_from_dicts


class JazzClient:
    def __init__(self, state_dir: str | None = None, artifact_dir: str | None = None, headed: bool = False):
        s = get_settings()
        self.state_dir = Path(state_dir or s.PLAYWRIGHT_STATE_DIR)
        self.artifact_dir = Path(artifact_dir or s.DEBUG_ARTIFACT_DIR)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.headed = headed or not s.JAZZ_HEADLESS
        self._pw = None
        self._ctx: BrowserContext | None = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(self.state_dir), headless=not self.headed, accept_downloads=True,
            executable_path=get_settings().JAZZ_CHROMIUM_EXECUTABLE or None,
            args=["--disable-dev-shm-usage"],
        )
        return self

    def __exit__(self, *exc):
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    def _page(self) -> Page:
        assert self._ctx is not None
        return self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def is_authenticated(self, page: Page) -> bool:
        try:
            return sel.LOGIN_PATH not in page.url and page.locator(sel.AUTHENTICATED_MARKER).is_visible()
        except Exception:
            return False

    def login(self, run_id: str = "auto") -> Page:
        s = get_settings()
        require_jazz(s)
        page = self._page()
        page.goto(s.JAZZ_URL, wait_until="domcontentloaded", timeout=s.JAZZ_PAGE_TIMEOUT_MS)
        if self.is_authenticated(page):
            return page
        if page.locator("input[name='diodid']").count() == 0:
            raise JazzPageChanged("Jazz login form not found")
        # Never screenshot or log this page: the password is present in the DOM.
        page.locator(sel.LOGIN_USERNAME).fill(s.JAZZ_UAN)
        page.locator(sel.LOGIN_PASSWORD).fill(s.JAZZ_PASSWORD)
        page.locator(sel.LOGIN_SUBMIT).click()
        try:
            page.wait_for_url("**/admin/vpbxadmin", timeout=s.JAZZ_PAGE_TIMEOUT_MS)
        except Exception:
            body = page.locator("body").inner_text().lower()
            if any(x in body for x in ("captcha", "otp", "verification code")):
                raise JazzBlocked("JAZZ_AUTH_BLOCKED: interactive challenge") from None
            raise JazzAuthFailed("Jazz did not accept configured credentials") from None
        if not self.is_authenticated(page):
            raise JazzAuthFailed("Jazz authenticated marker missing after login")
        try:
            from app.appwrite import repos

            repos.set_setting("last_successful_login", datetime.now(UTC).isoformat())
        except Exception:
            pass  # Login must remain usable when Appwrite is briefly unavailable.
        return page

    def ensure_auth(self, run_id: str = "auto") -> Page:
        s = get_settings()
        page = self._page()
        try:
            page.goto(s.JAZZ_URL, wait_until="domcontentloaded", timeout=s.JAZZ_PAGE_TIMEOUT_MS)
        except Exception as e:
            raise JazzTimeout("Jazz home navigation failed") from e
        if not self.is_authenticated(page):
            return self.login(run_id)
        try:
            from app.appwrite import repos

            repos.set_setting("last_successful_login", datetime.now(UTC).isoformat())
        except Exception:
            pass
        return page

    def _cdr_url(self, direction: str) -> str:
        if direction not in sel.CDR_PATHS:
            raise ValueError("direction must be INBOUND or OUTBOUND")
        return get_settings().JAZZ_URL.rstrip("/") + "/" + sel.CDR_PATHS[direction]

    def extension_mappings(self, page: Page) -> dict[str, tuple[str, str]]:
        """Read exact named extensions; shared/ambiguous names are never guessed."""
        url = get_settings().JAZZ_URL.rstrip("/") + "/extension_details"
        page.goto(url, wait_until="domcontentloaded", timeout=get_settings().JAZZ_PAGE_TIMEOUT_MS)
        if not self.is_authenticated(page):
            self.login()
            page.goto(url, wait_until="domcontentloaded", timeout=get_settings().JAZZ_PAGE_TIMEOUT_MS)
        table = page.locator("#example1")
        table.wait_for(state="visible", timeout=get_settings().JAZZ_PAGE_TIMEOUT_MS)
        length = page.locator("#example1_length select")
        if length.count():
            length.select_option("100")
        mappings: dict[str, tuple[str, str]] = {}
        for tr in table.locator("tbody tr").all():
            cells = [x.strip() for x in tr.locator("td").all_inner_texts()]
            if len(cells) < 5:
                continue
            name = re.sub(r"^ms\.?\s+", "", cells[4], flags=re.I).strip().lower()
            if name in ("saima", "kiran"):
                mobile = re.sub(r"\D", "", cells[3])
                source = mobile[1:] if len(mobile) == 11 and mobile.startswith("0") else mobile
                mappings[name] = (source, cells[0])
        return mappings

    def _dated_table(self, page: Page, direction: str, date_str: str) -> str:
        """Use the portal's own AJAX date search, which returns every matching row.

        DataTables pagination is client-side: the response contains all rows,
        independent of the current 10/25/50/100 page-size setting.
        """
        assert self._ctx is not None
        url = self._cdr_url(direction)
        s = get_settings()
        for attempt in range(2):
            page.goto(url, wait_until="domcontentloaded", timeout=s.JAZZ_PAGE_TIMEOUT_MS)
            if not self.is_authenticated(page):
                self.login()
                continue
            response = self._ctx.request.get(
                url, params={"start_date": date_str, "end_date": date_str},
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=s.JAZZ_PAGE_TIMEOUT_MS,
            )
            if response.ok and "id=\"table_cdr\"" in response.text():
                return response.text()
            if attempt == 0:
                self.login()
        raise JazzPageChanged("Dated Jazz CDR table missing")

    def iter_call_rows(self, page: Page, date_str: str, run_id: str = "auto") -> list[JazzRow]:
        rows: list[JazzRow] = []
        assert self._ctx is not None
        for direction in ("OUTBOUND", "INBOUND"):
            fragment = self._dated_table(page, direction, date_str)
            scratch = self._ctx.new_page()
            try:
                scratch.set_content(fragment)
                table = scratch.locator(sel.CALL_TABLE)
                headers = [h.strip() for h in table.locator("thead th").all_inner_texts()]
                if not headers or "Call Status" not in headers:
                    raise JazzPageChanged("Jazz CDR headers changed")
                for tr in table.locator("tbody tr").all():
                    cells = [c.strip() for c in tr.locator("td").all_inner_texts()]
                    if len(cells) != len(headers):
                        continue  # DataTables' empty-result row
                    row = rows_from_dicts(headers, [cells])[0]
                    row.direction_raw = direction.lower()
                    link = tr.locator(sel.RECORDING_DETAIL_LINK)
                    if link.count():
                        row.recording_url = link.first.get_attribute("href") or ""
                        row.row_id = row.recording_url.rstrip("/").rsplit("/", 1)[-1]
                        row.has_recording = bool(row.recording_url)
                    row.extra["bill_seconds"] = parse_duration(cells[headers.index("Bill Sec")])
                    if not row.started_at:
                        raise JazzPageChanged("Jazz CDR timestamp could not be parsed")
                    rows.append(row)
            finally:
                scratch.close()
        return rows

    def recording_source(self, detail_url: str) -> str | None:
        """Resolve CDR detail link to the actual WAV source; absent source is normal."""
        assert self._ctx is not None
        self._assert_jazz_url(detail_url)
        for _ in range(2):
            response = self._ctx.request.get(detail_url, timeout=get_settings().JAZZ_PAGE_TIMEOUT_MS)
            body = response.text() if response.ok else ""
            match = re.search(r"<source\b[^>]*\bsrc=[\"']([^\"']+)", body, re.I)
            if match:
                url = urljoin(detail_url, html.unescape(match.group(1)))
                self._assert_jazz_url(url)
                return url
            if "loginvpbx" in body or response.status in (401, 403):
                self.login()
                continue
            return None
        raise JazzAuthFailed("Jazz recording session expired")

    def download_recording(self, detail_url: str, dest: Path) -> bool:
        assert self._ctx is not None
        source = self.recording_source(detail_url)
        if not source:
            return False
        for _ in range(2):
            response = self._ctx.request.get(source, timeout=get_settings().JAZZ_PAGE_TIMEOUT_MS)
            if response.ok and response.body() and not response.body().lstrip().startswith(b"<"):
                dest.write_bytes(response.body())
                return True
            if response.status in (401, 403):
                self.login()
                continue
            raise JazzDownloadFailed("Jazz recording download failed")
        raise JazzAuthFailed("Jazz recording session expired")

    @staticmethod
    def _assert_jazz_url(url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "businessline.jazz.com.pk":
            raise JazzDownloadFailed("Unexpected recording URL host")
