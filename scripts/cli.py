"""Admin CLI — same services as the scheduler (no duplicated logic)."""

from __future__ import annotations

import os
import sys

import typer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "backend"))

app = typer.Typer()


@app.command()
def sync_jazz(date: str = typer.Option("", help="YYYY-MM-DD; default today+overlap")):
    from app.ingestion.runner import sync_date, sync_window

    typer.echo(sync_date(date) if date else sync_window())


def sync_jazz_result(d: str) -> dict:
    from app.ingestion.runner import sync_date

    return sync_date(d)


@app.command()
def process_jobs(once: bool = False):
    import uuid

    from app.jobs.worker import process_one

    wid = f"cli-{uuid.uuid4().hex[:4]}"
    n = 0
    while process_one(wid):
        n += 1
        if once:
            break
    typer.echo(f"processed {n} jobs")


@app.command()
def retry_failed():
    from appwrite.query import Query

    from app.appwrite import repos

    rows = repos.list_docs("processing_jobs", [Query.equal("status", "FAILED")], limit=100)
    for r in rows:
        repos.update_doc("processing_jobs", r["$id"], {"status": "QUEUED", "locked_by": ""})
    typer.echo(f"requeued {len(rows)}")


@app.command()
def regenerate_report(reporting_date: str):
    import json

    from appwrite.query import Query

    from app.appwrite import repos
    from app.config.settings import get_settings
    from app.reporting.compute import compute_report

    s = get_settings()
    calls = repos.list_docs("calls", [Query.equal("reporting_date", reporting_date)], limit=500)
    grades = {}
    for c in calls:
        g = repos.get_grade(c.get("$id", ""))
        if g:
            try:
                grades[c["$id"]] = json.loads(g.get("result_json", "{}") or "{}")
            except Exception:
                pass
    metrics = compute_report(calls, grades, threshold=s.LOW_SCORE_THRESHOLD)
    repos.save_report(reporting_date, "COMPLETE", metrics)
    typer.echo(f"report {reporting_date}: {metrics.get('total_calls', 0)} calls")


@app.command()
def cleanup_expired_audio(dry_run: bool = False):
    from app.retention.worker import cleanup_expired_audio as _clean

    typer.echo(_clean(dry_run=dry_run))


@app.command()
def inspect_jazz():
    typer.echo("Optional diagnostic: uv run python ../../scripts/jazz_inspect.py")


@app.command()
def health_check():
    from app.appwrite import repos

    repos.list_docs("app_settings", limit=1)
    typer.echo("Appwrite OK")


if __name__ == "__main__":
    app()
