"""Backend settings — validated at startup. Never logs secret values."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root .env regardless of process working directory.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_FILE = str(_REPO_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "development"
    TZ: str = "Asia/Karachi"
    APP_TIMEZONE: str = "Asia/Karachi"

    JAZZ_URL: str = "https://businessline.jazz.com.pk/Businessvpbx/admin/vpbxadmin"
    JAZZ_UAN: str = ""
    JAZZ_PASSWORD: str = ""
    JAZZ_HEADLESS: bool = True
    JAZZ_SYNC_OVERLAP_MINUTES: int = 30
    JAZZ_PAGE_TIMEOUT_MS: int = 30000
    JAZZ_MAX_PAGES: int = 200
    JAZZ_CHROMIUM_EXECUTABLE: str = ""

    JAZZ_SYNC_CRON: str = "1 18 * * *"
    BUSINESS_DAY_START: str = "09:30"
    BUSINESS_DAY_END: str = "18:00"

    GEMINI_API_KEY: str = ""
    GEMINI_TRANSCRIBE_MODEL: str = "gemini-3.5-transcribe"
    GEMINI_GRADING_MODEL: str = "gemini-3.8-flash"
    GEMINI_ROMANIZER_MODEL: str = "gemini-3.8-flash"
    GEMINI_TIMEOUT_SECONDS: int = 120
    GEMINI_MAX_OUTPUT_TOKENS: int = 16384
    GEMINI_REQUESTS_PER_MINUTE: float = 2
    GEMINI_DURABLE_RATE_LIMIT: bool = True

    @field_validator("GEMINI_REQUESTS_PER_MINUTE")
    @classmethod
    def _positive_rate(cls, value):
        if not 0 < value <= 10000:
            raise ValueError("GEMINI_REQUESTS_PER_MINUTE must be positive")
        return value

    PRODUCT_KEYWORDS: str = ""

    AUDIO_RETENTION_DAYS: int = 15
    DEBUG_ARTIFACT_RETENTION_DAYS: int = 7

    APPWRITE_ENDPOINT: str = "http://localhost/v1"
    APPWRITE_PROJECT_ID: str = ""
    APPWRITE_API_KEY: str = ""
    APPWRITE_DATABASE_ID: str = "call_grader"
    APPWRITE_RECORDINGS_BUCKET_ID: str = "call_recordings"

    INTERNAL_API_TOKEN: str = ""
    BACKEND_PORT: int = 8000
    BACKEND_HOST: str = "0.0.0.0"

    WORKER_POLL_INTERVAL_SECONDS: int = 5
    WORKER_LEASE_SECONDS: int = 300
    JOB_MAX_ATTEMPTS: int = 6
    JOB_RETRY_COOLDOWN_SECONDS: int = 1800
    SCHEDULER_CHECK_INTERVAL_SECONDS: int = 30

    LOW_SCORE_THRESHOLD: float = 6.0

    PLAYWRIGHT_STATE_DIR: str = "/tmp/yousuf-playwright-state"
    DEBUG_ARTIFACT_DIR: str = "/tmp/yousuf-debug-artifacts"
    LOCAL_AUDIO_DIR: str = "/tmp/yousuf-audio"

    @field_validator("APPWRITE_ENDPOINT")
    @classmethod
    def _strip_trailing(cls, v: str) -> str:
        return v.rstrip("/")


def validate_for_role(settings: Settings, role: str) -> list[str]:
    """Return list of missing env var names for a given service role."""
    missing: list[str] = []
    if role in ("api", "worker", "scheduler", "all"):
        for name in ("APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "APPWRITE_API_KEY"):
            if not getattr(settings, name):
                missing.append(name)
    if role in ("worker", "scheduler", "all") and not settings.GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if role in ("jazz", "worker", "scheduler", "all"):
        # Jazz creds only enforced when running the Jazz-capable worker/sync.
        pass
    return missing


def require_jazz(settings: Settings) -> None:
    missing = [n for n in ("JAZZ_UAN", "JAZZ_PASSWORD") if not getattr(settings, n)]
    if missing:
        raise RuntimeError(f"Missing required Jazz config: {', '.join(missing)} (set in .env)")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def mask_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) <= 5:
        return "****"
    return f"{digits[:2]}******{digits[-3:]}"
