"""Locators verified against the Jazz Business Line portal on 2026-09-25.

The two dated CDR screens return the complete matching table through an AJAX
GET. DataTables paginates that table only in the browser.
"""

LOGIN_USERNAME = "input[name='diodid']"
LOGIN_PASSWORD = "input[name='password']"
LOGIN_SUBMIT = "input[name='submit'][value='Log in']"
AUTHENTICATED_MARKER = "#dropdownMenuLink"
LOGIN_PATH = "/admin/user/loginvpbx"

REPORTS_MENU = "a:has-text('VPBX Reports')"
CDR_PATHS = {
    "OUTBOUND": "cdr_details_outbound",
    "INBOUND": "cdr_details_inbound",
}
FILTER_DATE_FROM = "#startDate"
FILTER_DATE_TO = "#endDate"
FILTER_SEARCH_BUTTON = "input[name='submit'][value='Search']"
CALL_TABLE = "#table_cdr"
TABLE_ROWS = "#table_cdr tbody tr"
PAGINATION_NEXT = "#table_cdr_next"
RESULT_COUNT = "#table_cdr_info"
RECORDING_DETAIL_LINK = "a[href*='/callrecording/']"
RECORDING_SOURCE = "audio source[src]"
RECORDING_DOWNLOAD = "a[download]"

COLUMN_HINTS = {
    "timestamp": ["call date time", "call date", "date time", "date/time"],
    "agent": ["ext no", "extension"],
    "client": ["client number"],
    "duration": ["duration"],
    "bill_seconds": ["bill sec"],
    "status": ["call status", "status"],
    "direction": ["call type", "direction"],
    "recording": ["call recording"],
    "caller": ["caller"],
    "callee": ["callee"],
}
