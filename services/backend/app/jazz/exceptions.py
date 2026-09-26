"""Jazz adapter exceptions — structured error taxonomy for the System page."""

from __future__ import annotations


class JazzError(Exception):
    code = "UNKNOWN"


class JazzAuthFailed(JazzError):
    code = "JAZZ_AUTH_FAILED"


class JazzPageChanged(JazzError):
    code = "JAZZ_PAGE_CHANGED"


class JazzTimeout(JazzError):
    code = "JAZZ_TIMEOUT"


class JazzDownloadFailed(JazzError):
    code = "JAZZ_DOWNLOAD_FAILED"


class JazzBlocked(JazzError):
    code = "JAZZ_AUTH_BLOCKED"
