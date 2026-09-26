from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import main


def test_internal_api_fails_closed_without_configured_token(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(INTERNAL_API_TOKEN=""))
    with pytest.raises(HTTPException) as exc:
        main.require_internal("anything")
    assert exc.value.status_code == 503


@pytest.mark.parametrize("token", [None, "wrong"])
def test_internal_api_rejects_missing_or_wrong_token(monkeypatch, token):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(INTERNAL_API_TOKEN="test-token"))
    with pytest.raises(HTTPException) as exc:
        main.require_internal(token)
    assert exc.value.status_code == 401


def test_internal_api_accepts_configured_token(monkeypatch):
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(INTERNAL_API_TOKEN="test-token"))
    assert main.require_internal("test-token") == "test-token"
