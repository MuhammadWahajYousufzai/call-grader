"""Appwrite server client (uses API key server-side only)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache

from appwrite.client import Client
from appwrite.services.storage import Storage
from appwrite.services.tables_db import TablesDB
from appwrite.services.users import Users

from app.config.settings import get_settings

_execution: ContextVar[tuple[str, str, str] | None] = ContextVar("appwrite_execution", default=None)


@contextmanager
def execution_credentials(endpoint: str, project: str, key: str):
    token = _execution.set((endpoint, project, key))
    try:
        yield
    finally:
        _execution.reset(token)


@lru_cache
def _configured_client() -> Client:
    s = get_settings()
    client = Client()
    client.set_endpoint(s.APPWRITE_ENDPOINT).set_project(s.APPWRITE_PROJECT_ID).set_key(s.APPWRITE_API_KEY)
    return client


def get_client() -> Client:
    current = _execution.get()
    if current:
        endpoint, project, key = current
        return Client().set_endpoint(endpoint).set_project(project).set_key(key)
    return _configured_client()


def tables() -> TablesDB:
    return TablesDB(get_client())


def storage() -> Storage:
    return Storage(get_client())


def users() -> Users:
    return Users(get_client())


def database_id() -> str:
    return get_settings().APPWRITE_DATABASE_ID


def bucket_id() -> str:
    return get_settings().APPWRITE_RECORDINGS_BUCKET_ID
