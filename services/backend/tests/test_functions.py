"""Execution limits, saved checkpoints, and credential isolation."""

import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest
from app.appwrite import client as aw
from app.functions import phases, pipeline


def test_execution_key_does_not_leak_to_next_invocation(monkeypatch):
    configured = Mock()
    monkeypatch.setattr(aw, "_configured_client", lambda: configured)
    with aw.execution_credentials("https://example.com/v1", "project", "first-key"):
        assert aw.get_client().get_headers()["x-appwrite-key"] == "first-key"
        with aw.execution_credentials("https://example.com/v1", "project", "second-key"):
            assert aw.get_client().get_headers()["x-appwrite-key"] == "second-key"
        assert aw.get_client().get_headers()["x-appwrite-key"] == "first-key"
    assert aw.get_client() is configured


def test_romanization_resumes_only_missing_segments(monkeypatch):
    segments = [{"$id": str(i), "sequence": i, "raw_text": "speech", "roman_urdu_text": ""} for i in range(61)]
    monkeypatch.setattr(phases.repos, "get_segments", lambda call: segments)
    monkeypatch.setattr(phases.repos, "update_call", Mock())
    ensure = Mock()
    monkeypatch.setattr(phases.repos, "ensure_job", ensure)
    def persist(table, row_id, patch):
        segments[int(row_id)].update(patch)
    monkeypatch.setattr(phases.repos, "update_doc", persist)
    from app.ai import workflows
    romanizer = Mock(side_effect=lambda batch: [{**s, "roman_urdu_text": "roman"} for s in batch])
    monkeypatch.setattr(workflows, "romanize_segments", romanizer)
    call = {"$id": "call", "reporting_date": "2026-09-25"}
    for _ in range(2):
        with pytest.raises(phases.ContinueJob):
            phases.romanize_batch(call)
    phases.romanize_batch(call)
    assert [len(c.args[0]) for c in romanizer.call_args_list] == [30, 30, 1]
    assert all(s["roman_urdu_text"] == "roman" for s in segments)
    ensure.assert_called_once_with("GRADE", "call", "2026-09-25")


def test_saved_discovery_resumes_next_date(monkeypatch):
    state = {"last_scheduled_reporting_date": "", "function_discovery_progress": json.dumps({
        "due": "2026-09-25", "dates": ["2026-09-24", "2026-09-25"], "index": 1, "added_prior": ""})}
    monkeypatch.setattr(pipeline.repos, "get_setting", lambda key: state.get(key, ""))
    monkeypatch.setattr(pipeline.repos, "set_setting", lambda key, value: state.update({key: value}))
    @contextmanager
    def lease(name):
        yield True
    monkeypatch.setattr(pipeline, "leased", lease)
    monkeypatch.setattr(pipeline, "latest_processing_date", lambda *args: date(2026, 9, 25))
    sync = Mock(return_value={"status": "SUCCESS"})
    monkeypatch.setattr(pipeline, "sync_date", sync)
    monkeypatch.setattr(pipeline, "due_jobs", lambda: 0)
    pipeline.run_sync()
    sync.assert_called_once_with("2026-09-25", max_reporting_date="2026-09-25", min_reporting_date=None)
    assert state["last_scheduled_reporting_date"] == "2026-09-25"
    assert state["function_discovery_progress"] == ""


def test_function_schedules_are_utc_and_execution_is_private():
    config = json.loads((Path(__file__).resolve().parents[3] / "appwrite.config.json").read_text())
    functions = {f["$id"]: f for f in config["functions"]}
    assert functions["call-grader-sync"]["schedule"] == "1 13 * * *"
    assert functions["call-grader-maintenance"]["schedule"] == "30 21 * * *"
    assert functions["call-grader-worker"]["timeout"] == 900
    assert all(f["execute"] == [] for f in functions.values())


def test_last_transcription_checkpoint_does_not_redownload_or_retranscribe(monkeypatch):
    monkeypatch.setattr(phases.repos, "get_setting", lambda key: json.dumps({"sha": "same", "done": True, "chunk": 2}))
    finish = Mock()
    monkeypatch.setattr(phases, "finish_transcription", finish)
    from app.jobs import worker
    download = Mock()
    monkeypatch.setattr(worker, "_download_storage_to_tmp", download)
    call = {"$id": "call", "recording_sha256": "same"}
    phases.transcribe_chunk(call)
    finish.assert_called_once_with(call)
    download.assert_not_called()


def test_private_key_scope_is_not_cached_between_fastapi_threadpool_requests():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    api = FastAPI()
    @api.get("/scope")
    def scope():
        return {"key": aw.get_client().get_headers()["x-appwrite-key"]}
    with aw.execution_credentials("https://example.com/v1", "project", "invocation-key"):
        assert TestClient(api).get("/scope").json() == {"key": "invocation-key"}


def test_deployment_reads_async_result_from_logs(monkeypatch):
    import importlib.util

    scripts = Path(__file__).resolve().parents[3] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("appwrite_deployment", scripts / "deploy_appwrite.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    responses = iter([{"$id": "execution"}, {"status": "completed", "responseStatusCode": 200,
        "logs": '{"chromium":true,"ffmpeg":true,"ffprobe":true}\nNative logs detected.'}])
    monkeypatch.setattr(module, "command", lambda *args, **kwargs: next(responses))
    assert module.execute("worker", {}, scripts, {}, ()) == {"chromium": True, "ffmpeg": True, "ffprobe": True}


def test_api_readiness_retries_only_runtime_startup_failure(monkeypatch):
    import importlib.util

    scripts = Path(__file__).resolve().parents[3] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("appwrite_readiness", scripts / "deploy_appwrite.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    responses = iter([
        {"$id": "cold"},
        {"status": "failed", "errors": "Timed out waiting for runtime."},
        {"$id": "warm"},
        {"status": "completed", "responseStatusCode": 200, "logs": 'FUNCTION_RESULT_JSON={"ok":true,"appwrite":true}'},
    ])
    commands = []
    def run(args, *unused, **kwargs):
        commands.append(args)
        return next(responses)
    monkeypatch.setattr(module, "command", run)
    assert module.execute("api", {}, scripts, {}, (), readiness=True) == {"ok": True, "appwrite": True}
    starts = [args for args in commands if "create-execution" in args]
    assert len(starts) == 2
    assert all(args[-4:] == ["--path", "/health/ready", "--method", "GET"] for args in starts)


@pytest.mark.parametrize("canonical,recording,expected", [
    ("NO_ANSWER", True, "NOT_ELIGIBLE"), ("BUSY", True, "NOT_ELIGIBLE"),
    ("ANSWERED", False, "NO_RECORDING"),
])
def test_crash_after_metadata_persistence_finishes_ineligible_calls(monkeypatch, canonical, recording, expected):
    from app.jobs import worker

    call = {"$id": "call", "pipeline_status": "METADATA_SAVED", "canonical_status": canonical,
            "recording_available": recording, "reporting_date": ""}
    monkeypatch.setattr(worker.repos, "list_docs", lambda *args, **kwargs: [call])
    update = Mock()
    enqueue = Mock()
    monkeypatch.setattr(worker.repos, "update_call", update)
    monkeypatch.setattr(worker.repos, "ensure_job", enqueue)
    assert worker.recover_incomplete_calls() == 0
    update.assert_called_once_with("call", {"pipeline_status": expected})
    enqueue.assert_not_called()


@pytest.mark.parametrize("fails", [False, True])
def test_function_temp_audio_is_removed_after_success_or_failure(monkeypatch, fails):
    import asyncio

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    from infra.appwrite import common

    directories = []
    async def workload(context, role, directory):
        path = Path(directory)
        directories.append(path)
        (path / "recording.wav").write_bytes(b"temporary audio")
        if fails:
            raise RuntimeError("workload failed")
        return {"ok": True}
    monkeypatch.setattr(common, "_run_child", workload)
    if fails:
        with pytest.raises(RuntimeError, match="workload failed"):
            asyncio.run(common.run_child(None, "worker"))
    else:
        assert asyncio.run(common.run_child(None, "worker")) == {"ok": True}
    assert directories and not directories[0].exists()


@pytest.mark.parametrize("text,expected", [("", {}), ('{"action":"runtime-check"}', {"action": "runtime-check"})])
def test_cron_empty_body_is_safe_without_reading_body_json(monkeypatch, text, expected):
    from types import SimpleNamespace

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[3]))
    from infra.appwrite.common import request_body

    class Request:
        body_text = text
        @property
        def body_json(self):
            raise AssertionError("Cron's empty JSON property must not be read")
    assert request_body(SimpleNamespace(req=Request())) == expected
