"""Appwrite server client (uses API key server-side only)."""

from __future__ import annotations

from functools import lru_cache

from appwrite.client import Client
from appwrite.services.storage import Storage
from appwrite.services.tables_db import TablesDB
from appwrite.services.users import Users

from app.config.settings import get_settings


@lru_cache
def get_client() -> Client:
    s = get_settings()
    client = Client()
    client.set_endpoint(s.APPWRITE_ENDPOINT).set_project(s.APPWRITE_PROJECT_ID).set_key(s.APPWRITE_API_KEY)
    return client


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
