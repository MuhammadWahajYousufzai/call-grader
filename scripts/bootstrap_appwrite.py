"""Idempotent Appwrite bootstrap: database, tables, columns, indexes, bucket. Safe to re-run."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "backend"))

from app.appwrite.schema import DEFAULT_BUSINESS_RULES, DEFAULT_SETTINGS, TABLES  # noqa: E402


def _client():
    from appwrite.client import Client

    endpoint = os.environ.get("APPWRITE_ENDPOINT", "http://localhost/v1")
    project = os.environ["APPWRITE_PROJECT_ID"]
    key = os.environ["APPWRITE_API_KEY"]
    return Client().set_endpoint(endpoint).set_project(project).set_key(key)


def _columns_of(tables_svc, db_id: str, table_id: str) -> set[str]:
    try:
        res = tables_svc.list_columns(database_id=db_id, table_id=table_id)
        cols = res.get("columns", []) if isinstance(res, dict) else getattr(res, "columns", [])
        return {c.get("key") for c in cols if isinstance(c, dict)}
    except Exception:
        return set()


def _indexes_of(tables_svc, db_id: str, table_id: str) -> set[str]:
    try:
        res = tables_svc.list_indexes(database_id=db_id, table_id=table_id)
        idxs = res.get("indexes", []) if isinstance(res, dict) else getattr(res, "indexes", [])
        return {i.get("key") for i in idxs if isinstance(i, dict)}
    except Exception:
        return set()


def ensure_table(tables_svc, db_id: str, table_id: str, spec: dict) -> None:
    from appwrite.exception import AppwriteException

    try:
        tables_svc.get_table(database_id=db_id, table_id=table_id)
        print(f"  table '{table_id}' exists")
    except AppwriteException as e:
        if getattr(e, "code", 0) not in (404,):
            raise
        tables_svc.create_table(database_id=db_id, table_id=table_id, name=spec["name"])
        print(f"  table '{table_id}' created")

    existing = _columns_of(tables_svc, db_id, table_id)
    for attr in spec.get("attributes", []):
        if attr["key"] in existing:
            continue
        t = attr["type"]
        try:
            if t == "string":
                # NOTE: create_string_column is deprecated in this SDK generation;
                # text columns are the supported equivalent (variable length, so no
                # size argument). Existing varchar columns from earlier runs are
                # left untouched — the key check above keeps this idempotent.
                tables_svc.create_text_column(database_id=db_id, table_id=table_id,
                                              key=attr["key"],
                                              required=bool(attr.get("required", False)))
            elif t == "integer":
                tables_svc.create_integer_column(database_id=db_id, table_id=table_id,
                                                 key=attr["key"], required=bool(attr.get("required", False)))
            elif t == "float":
                tables_svc.create_float_column(database_id=db_id, table_id=table_id,
                                               key=attr["key"], required=bool(attr.get("required", False)))
            elif t == "boolean":
                tables_svc.create_boolean_column(database_id=db_id, table_id=table_id,
                                                 key=attr["key"], required=bool(attr.get("required", False)))
            elif t == "datetime":
                tables_svc.create_datetime_column(database_id=db_id, table_id=table_id,
                                                  key=attr["key"], required=bool(attr.get("required", False)))
            print(f"    + column {table_id}.{attr['key']}")
        except Exception as e:
            msg = str(e).lower()
            if "already" in msg or "exists" in msg:
                continue
            # Appwrite can report a misleading size-limit error when the column
            # actually exists (stale list right after provisioning) — re-check.
            if "maximum number or size" in msg and attr["key"] in _columns_of(tables_svc, db_id, table_id):
                continue
            print(f"    ! column {table_id}.{attr['key']}: {e}")
    time.sleep(2)  # allow Appwrite to finish column provisioning
    from appwrite.enums.tables_db_index_type import TablesDBIndexType

    existing_idx = _indexes_of(tables_svc, db_id, table_id)
    for idx in spec.get("indexes", []):
        if idx["key"] in existing_idx:
            continue
        try:
            itype = TablesDBIndexType.UNIQUE if idx["type"] == "unique" else TablesDBIndexType.KEY
            tables_svc.create_index(database_id=db_id, table_id=table_id, key=idx["key"],
                                    type=itype, columns=idx["attributes"])
            print(f"    + index {table_id}.{idx['key']}")
        except Exception as e:
            if "already" in str(e).lower() or "exists" in str(e).lower():
                continue
            print(f"    ! index {table_id}.{idx['key']}: {e}")


def ensure_bucket(storage_svc, bucket_id: str) -> None:
    from appwrite.exception import AppwriteException
    from appwrite.permission import Permission
    from appwrite.role import Role

    try:
        storage_svc.get_bucket(bucket_id=bucket_id)
        print(f"  bucket '{bucket_id}' exists")
        return
    except AppwriteException as e:
        if getattr(e, "code", 0) not in (404,):
            raise
    storage_svc.create_bucket(
        bucket_id=bucket_id, name="call_recordings",
        permissions=[Permission.read(Role.users()), Permission.write(Role.users())],
        file_security=True, enabled=True, encryption=True, antivirus=True,
    )
    print(f"  bucket '{bucket_id}' created (private)")


def seed(tables_svc, db_id: str) -> None:
    from appwrite.id import ID
    from appwrite.query import Query

    def find(table: str, field: str, value: str) -> list:
        res = tables_svc.list_rows(database_id=db_id, table_id=table,
                                   queries=[Query.equal(field, value), Query.limit(2)])
        if isinstance(res, dict):
            return res.get("rows", [])
        return getattr(res, "rows", []) or []

    for name in ("Saima", "Kiran"):
        try:
            if not find("agents", "name", name):
                tables_svc.create_row(database_id=db_id, table_id="agents", row_id=ID.unique(),
                                      data={"name": name, "active": True})
                print(f"  seeded agent {name}")
        except Exception as e:
            print(f"  ! seed agent {name}: {e}")
    for rule in DEFAULT_BUSINESS_RULES:
        try:
            if not find("business_rules", "key", rule["key"]):
                tables_svc.create_row(database_id=db_id, table_id="business_rules", row_id=ID.unique(),
                                      data={**rule, "version": 1})
                print(f"  seeded rule {rule['key']}")
        except Exception as e:
            print(f"  ! seed rule {rule['key']}: {e}")
    for s in DEFAULT_SETTINGS:
        try:
            if not find("app_settings", "key", s["key"]):
                tables_svc.create_row(database_id=db_id, table_id="app_settings", row_id=ID.unique(), data=s)
                print(f"  seeded setting {s['key']}")
        except Exception as e:
            print(f"  ! seed setting {s['key']}: {e}")


def main() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    try:
        from dotenv import load_dotenv  # optional

        load_dotenv(env_path)
    except Exception:
        pass
    # also load plain .env manually (no python-dotenv dependency)
    try:
        with env_path.open() as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
    except FileNotFoundError:
        pass
    for var in ("APPWRITE_PROJECT_ID", "APPWRITE_API_KEY"):
        if not os.environ.get(var):
            raise SystemExit(f"Missing {var} — copy .env.example to .env and fill Appwrite values")
    db_id = os.environ.get("APPWRITE_DATABASE_ID", "call_grader")
    bucket_id = os.environ.get("APPWRITE_RECORDINGS_BUCKET_ID", "call_recordings")
    client = _client()
    from appwrite.services.storage import Storage
    from appwrite.services.tables_db import TablesDB

    tables_svc, storage_svc = TablesDB(client), Storage(client)
    print(f"Bootstrapping Appwrite (db={db_id})")
    from appwrite.exception import AppwriteException

    try:
        tables_svc.get(database_id=db_id)
        print(f"  database '{db_id}' exists")
    except AppwriteException as e:
        if getattr(e, "code", 0) not in (404,):
            raise
        tables_svc.create(database_id=db_id, name="Call Grader")
        print(f"  database '{db_id}' created")
    for table_id, spec in TABLES.items():
        ensure_table(tables_svc, db_id, table_id, spec)
    ensure_bucket(storage_svc, bucket_id)
    seed(tables_svc, db_id)
    print("Bootstrap complete — re-running is safe (no data destroyed).")


if __name__ == "__main__":
    main()
