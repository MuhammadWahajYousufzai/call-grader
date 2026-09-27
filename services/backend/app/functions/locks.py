"""Transactional leases serialize scheduled and chained Function executions."""

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from appwrite.exception import AppwriteException

from app.appwrite import client as aw
from app.appwrite import repos


class Lease:
    def __init__(self, name: str, seconds: int = 1200):
        self.name = name
        self.row_id = "lease_" + sha256(name.encode()).hexdigest()[:28]
        self.owner = uuid.uuid4().hex
        self.seconds = seconds

    def _value(self, expires):
        return json.dumps({"owner": self.owner, "expires": expires.isoformat()})

    def _replace(self, value, predicate):
        db = aw.tables()
        txn = repos._as_dict(db.create_transaction(ttl=60))["$id"]
        committed = False
        try:
            # Stage first: Appwrite captures the row version before we inspect
            # the committed owner. A competing takeover makes commit conflict.
            db.update_row(database_id=aw.database_id(), table_id="app_settings",
                          row_id=self.row_id, data={"value": value}, transaction_id=txn)
            row = repos._as_dict(db.get_row(database_id=aw.database_id(),
                                           table_id="app_settings", row_id=self.row_id))
            if not predicate(json.loads(row["value"])):
                return False
            db.update_transaction(transaction_id=txn, commit=True)
            committed = True
            return True
        except AppwriteException as exc:
            if exc.code in (404, 409):
                return False
            raise
        finally:
            if not committed:
                try:
                    db.update_transaction(transaction_id=txn, rollback=True)
                except AppwriteException as exc:
                    # A conflicting commit is already terminal in Appwrite.
                    if exc.type != "transaction_not_ready":
                        raise

    def acquire(self):
        now = datetime.now(UTC)
        value = self._value(now + timedelta(seconds=self.seconds))
        try:
            repos.create_doc("app_settings", {"key": "function_lease_" + self.name,
                                             "value": value}, self.row_id)
            return True
        except AppwriteException as exc:
            if exc.code != 409:
                raise
        return self._replace(value, lambda old: datetime.fromisoformat(old["expires"]) <= now)

    def release(self):
        return self._replace(self._value(datetime.now(UTC)), lambda old: old["owner"] == self.owner)


@contextmanager
def leased(name: str):
    lease = Lease(name)
    acquired = lease.acquire()
    try:
        yield acquired
    finally:
        if acquired:
            lease.release()
