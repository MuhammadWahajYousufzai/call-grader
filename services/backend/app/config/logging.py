"""Structured JSON logging with secret redaction."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

SECRET_KEYS = ("password", "api_key", "apikey", "token", "authorization", "secret", "uan")


def _redact(obj):
    if isinstance(obj, dict):
        return {k: ("***" if any(s in k.lower() for s in SECRET_KEYS) else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(x) for x in obj]
    return obj


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.Record) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", "backend"),
            "event": getattr(record, "event", record.getMessage()),
            "run_id": getattr(record, "run_id", None),
            "job_id": getattr(record, "job_id", None),
            "call_id": getattr(record, "call_id", None),
            "severity": getattr(record, "severity", record.levelname),
            "message": record.getMessage(),
        }
        extra = getattr(record, "extra_data", None)
        if extra:
            payload["data"] = _redact(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(service: str = "backend") -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    logger = logging.getLogger(service)
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
