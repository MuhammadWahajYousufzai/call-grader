"""One discovery date or pipeline job per execution; Appwrite cron resumes crashes."""

import json
import os
from datetime import datetime, time, timedelta

from appwrite.query import Query
from appwrite.services.functions import Functions

from app.appwrite import client as aw
from app.appwrite import repos
from app.domain.helpers import latest_processing_date
from app.functions.locks import leased
from app.ingestion.runner import PKT, discovery_dates, newest_jazz_call, sync_date
from app.jobs.queue import recover_stale_leases


def dispatch(function_id: str, body: dict | None = None):
    if not function_id:
        raise RuntimeError("Function ID is not configured")
    return repos._as_dict(Functions(aw.get_client()).create_execution(
        function_id=function_id, body=json.dumps(body or {}), xasync=True))


def due_jobs():
    return repos.count_docs("processing_jobs", [
        Query.equal("status", "QUEUED"),
        Query.less_than_equal("reporting_date", latest_processing_date().isoformat()),
        Query.less_than_equal("next_attempt_at", repos.now_iso()),
    ])


def run_sync(request: dict | None = None):
    request = request or {}
    more = False
    with leased("discovery") as acquired:
        if not acquired:
            return {"status": "BUSY"}
        if request.get("date"):
            # Explicit admin requests are asynchronous too.
            result = sync_date(request["date"], max_reporting_date=latest_processing_date().isoformat())
        else:
            now = datetime.now(PKT)
            due = latest_processing_date(now).isoformat()
            if repos.get_setting("last_scheduled_reporting_date") >= due:
                return {"status": "UP_TO_DATE"}
            saved = repos.get_setting("function_discovery_progress")
            progress = json.loads(saved) if saved else None
            if not progress:
                latest = newest_jazz_call()
                if not latest and due < now.date().isoformat():
                    return {"status": "WAITING_FOR_1801"}
                dates = discovery_dates(datetime.combine(datetime.fromisoformat(due).date(), time(18, 1), PKT))
                prior = (datetime.fromisoformat(due).date() - timedelta(days=1)).isoformat()
                added_prior = ""
                if latest and dates[0] > prior:
                    dates.insert(0, prior)
                    added_prior = prior
                progress = {"due": due, "dates": dates, "index": 0, "added_prior": added_prior}
                repos.set_setting("function_discovery_progress", json.dumps(progress))
            day = progress["dates"][progress["index"]]
            result = sync_date(day, max_reporting_date=progress["due"],
                               min_reporting_date=progress["due"] if day == progress["added_prior"] else None)
            if result.get("status") == "SUCCESS":
                progress["index"] += 1
                more = progress["index"] < len(progress["dates"])
                if more:
                    repos.set_setting("function_discovery_progress", json.dumps(progress))
                else:
                    repos.set_setting("last_scheduled_reporting_date", progress["due"])
                    repos.set_setting("function_discovery_progress", "")
    if more:
        dispatch(os.environ["APPWRITE_SYNC_FUNCTION_ID"])
    if result.get("status") == "SUCCESS" and due_jobs():
        dispatch(os.environ["APPWRITE_WORKER_FUNCTION_ID"])
    return result


def run_worker():
    from app.jobs.worker import process_one, recover_incomplete_calls

    with leased("worker") as acquired:
        if not acquired:
            return {"status": "BUSY"}
        recover_stale_leases()
        recover_incomplete_calls()
        processed = process_one("function-" + os.environ.get("APPWRITE_FUNCTION_ID", "worker"))
        remaining = due_jobs()
    # Release before dispatch so the successor can acquire the lease.
    if remaining:
        dispatch(os.environ["APPWRITE_WORKER_FUNCTION_ID"])
    return {"processed": processed, "remaining_due": remaining}


def run_maintenance():
    from app.retention.worker import cleanup_debug_artifacts, cleanup_expired_audio

    with leased("maintenance") as acquired:
        if not acquired:
            return {"status": "BUSY"}
        cleanup_expired_audio()
        cleanup_debug_artifacts()
    return {"status": "SUCCESS"}
