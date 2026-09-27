"""Sanitized cases from the verified 2026-09-25 Jazz CDR layout."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.helpers import dedupe_key, latest_processing_date, normalize_status, retention_due
from app.ingestion import runner
from app.jazz.parser import parse_started_at, rows_from_dicts
from app.jobs import queue, worker
from app.reporting.compute import compute_report
from app.retention import worker as retention
from app.transcription import service as transcription

PKT = ZoneInfo("Asia/Karachi")


def test_verified_outbound_and_inbound_columns(monkeypatch):
    monkeypatch.setattr(runner.repos, "find_agent_by_jazz", lambda _: None)
    outbound = rows_from_dicts(
        ["Call Date Time", "Ext No", "Client Number", "Duration", "Bill Sec",
         "Call Status", "Call Type", "Call Recording"],
        [["2026-09-25 16:31:44", "3092220817", "03000000000", "00:01:02",
          "00:00:49", "ANSWERED", "outbound", "Recording"]],
    )[0]
    inbound = rows_from_dicts(
        ["Call Date Time", "Client Number", "Ext No", "Duration", "Bill Sec",
         "Call Status", "Call Type", "Call Recording"],
        [["2026-09-25 16:34:01", "03230000000", "Missed Call -", "00:00:13",
          "00:00:13", "ANSWERED", "inbound", "Recording"]],
    )[0]
    out_doc = runner.row_to_call_doc(outbound)
    in_doc = runner.row_to_call_doc(inbound)
    assert out_doc["direction"] == "OUTBOUND"
    assert out_doc["raw_customer_number"] == "03000000000"
    assert out_doc["jazz_agent_identifier"] == "3092220817"
    assert in_doc["direction"] == "INBOUND"
    assert in_doc["raw_customer_number"] == "03230000000"
    assert in_doc["jazz_agent_identifier"] == "Missed Call -"
    assert outbound.started_at.tzinfo == PKT
    assert normalize_status("NO ANSWER") == "NO_ANSWER"
    assert normalize_status("BUSY") == "BUSY"
    assert normalize_status("ANSWERED") == "ANSWERED"


def test_recording_id_shared_by_distinct_inbound_legs():
    base = dict(direction="INBOUND", customer_number="03230000000",
                agent_identifier="1002", duration_seconds=13, row_id="1790334176.7793930")
    a = dedupe_key(started_at_iso="2026-09-25T16:04:14+05:00", **base)
    b = dedupe_key(started_at_iso="2026-09-25T16:04:02+05:00", **base)
    assert a != b
    assert a == dedupe_key(started_at_iso="2026-09-25T16:04:14+05:00", **base)


def test_first_run_and_cursor_overlap(monkeypatch):
    now = datetime(2026, 9, 25, 19, 40, tzinfo=PKT)
    monkeypatch.setattr(runner, "newest_jazz_call", lambda: None)
    assert runner.discovery_dates(now) == ["2026-09-25"]
    monkeypatch.setattr(runner, "newest_jazz_call", lambda: {
        "actual_started_at": datetime(2026, 9, 24, 23, 45, tzinfo=PKT).astimezone(UTC).isoformat()
    })
    assert runner.discovery_dates(now) == ["2026-09-24", "2026-09-25"]


def test_retention_uses_source_call_time():
    actual = parse_started_at("2026-09-01 09:00:00")
    assert retention_due(actual, 15) == actual + timedelta(days=15)


def test_restart_after_download_reuses_storage(monkeypatch):
    updates = []
    queued = []
    monkeypatch.setattr(worker.repos, "update_call", lambda cid, patch: updates.append(patch))
    monkeypatch.setattr(worker.repos, "ensure_job", lambda *args: queued.append(args))
    worker.do_download({"$id": "call1", "recording_storage_file_id": "stored-file",
                        "reporting_date": "2026-09-25"})
    assert updates == [{"pipeline_status": "TRANSCRIPTION_PENDING"}]
    assert queued == [("TRANSCRIBE", "call1", "2026-09-25")]


def test_ai_failure_keeps_existing_recording_and_retries(monkeypatch):
    job = {"$id": "job1", "job_type": "TRANSCRIBE", "call_id": "call1"}
    call = {"$id": "call1", "pipeline_status": "AUDIO_VALIDATED",
            "recording_storage_file_id": "stored-file", "retry_count": 0}
    failures = []
    monkeypatch.setattr(worker, "claim_next_job", lambda _: job)
    monkeypatch.setattr(worker.repos, "get_doc", lambda *_: call)
    monkeypatch.setattr(worker.repos, "update_call", lambda *args: None)
    monkeypatch.setitem(worker.HANDLERS, "TRANSCRIBE",
                        lambda _: (_ for _ in ()).throw(RuntimeError("Gemini unavailable")))
    monkeypatch.setattr(worker, "fail_job", lambda *args, **kwargs: failures.append((args, kwargs)))
    assert worker.process_one("worker1")
    assert failures and failures[0][1]["retryable"] is True
    assert call["recording_storage_file_id"] == "stored-file"


def test_report_waits_for_all_calls_before_coaching(monkeypatch):
    calls = [
        {"$id": "a", "direction": "OUTBOUND", "canonical_status": "ANSWERED",
         "pipeline_status": "COMPLETE", "recording_storage_file_id": "audio"},
        {"$id": "b", "direction": "OUTBOUND", "canonical_status": "ANSWERED",
         "pipeline_status": "TRANSCRIPTION_PENDING", "recording_storage_file_id": "audio"},
    ]
    saved = []
    monkeypatch.setattr(worker.repos, "list_docs", lambda *_args, **_kwargs: calls)
    monkeypatch.setattr(worker.repos, "get_grade", lambda *_: None)
    monkeypatch.setattr(worker.repos, "save_report", lambda *args, **kwargs: saved.append((args, kwargs)))
    monkeypatch.setattr("app.ai.workflows.daily_coaching_summary",
                        lambda *_: (_ for _ in ()).throw(AssertionError("summary ran too early")))
    worker.do_report("2026-09-25")
    assert saved[0][0][1] == "PROCESSING"


def test_silent_audio_is_terminal_and_does_not_fallback(monkeypatch, tmp_path):
    from app.ai import gemini
    calls = []
    def generate(*args, **kwargs):
        calls.append(kwargs)
        return {"candidates": [{"content": {"parts": [{"text": ""}]}, "finishReason": "STOP"}]}
    monkeypatch.setattr(gemini, "generate", generate)
    audio = tmp_path / "silence.wav"
    audio.write_bytes(b"fixture")
    assert transcription.transcribe_file(audio) == []
    assert len(calls) == 1 and calls[0]["transcription"] is True
    report = compute_report([{"$id": "silent", "direction": "OUTBOUND",
                              "canonical_status": "ANSWERED", "pipeline_status": "NO_SPEECH",
                              "recording_storage_file_id": "stored"}], {})
    assert report["still_processing"] == 0
    assert report["no_speech_calls"] == 1


def test_ungradable_call_is_terminal_without_fabricated_score(monkeypatch):
    saved = []
    call = {"$id": "call1", "reporting_date": "2026-09-25", "duration_seconds": 17,
            "agent_name_snapshot": "Unassigned"}
    monkeypatch.setattr(worker.repos, "update_call", lambda *args: saved.append(args))
    monkeypatch.setattr(worker.repos, "get_segments", lambda *_: [
        {"sequence": 0, "speaker_role": "Unknown", "raw_text": "[unclear]"}])
    monkeypatch.setattr(worker.repos, "list_docs", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(worker.repos, "ensure_report_job", lambda *_: None)
    monkeypatch.setattr("app.ai.workflows.grade_call",
                        lambda *_: (_ for _ in ()).throw(ValueError("No applicable dimensions to score")))
    monkeypatch.setattr(worker.repos, "save_grade",
                        lambda *_: (_ for _ in ()).throw(AssertionError("fabricated grade")))
    worker.do_grade(call)
    assert saved[-1][1]["pipeline_status"] == "UNGRADABLE"
    report = compute_report([{"$id": "call1", "direction": "OUTBOUND",
                              "canonical_status": "ANSWERED", "pipeline_status": "UNGRADABLE",
                              "recording_storage_file_id": "stored"}], {})
    assert report["still_processing"] == 0
    assert report["ungradable_calls"] == 1
    assert report["calls_graded"] == 0


def test_retention_does_not_claim_deletion_when_storage_fails(monkeypatch):
    row = {"$id": "call1", "recording_storage_file_id": "file1",
           "pipeline_status": "COMPLETE", "recording_deleted_at": ""}
    monkeypatch.setattr(retention.repos, "list_docs",
                        lambda table, *_args, **_kwargs: [row] if table == "calls" else [])

    class BrokenStorage:
        def delete_file(self, **_kwargs):
            raise RuntimeError("storage unavailable")

    monkeypatch.setattr(retention.aw, "storage", BrokenStorage)
    updated = []
    monkeypatch.setattr(retention.repos, "update_call", lambda *args: updated.append(args))
    result = retention.cleanup_expired_audio()
    assert result["deleted"] == 0
    assert result["skipped_active"] == 1
    assert updated == []


def test_retention_preserves_audio_for_transcription_retry(monkeypatch):
    row = {"$id": "call1", "recording_storage_file_id": "file1",
           "pipeline_status": "TRANSCRIPTION_FAILED", "recording_deleted_at": ""}
    monkeypatch.setattr(retention.repos, "list_docs",
                        lambda table, *_args, **_kwargs: [row] if table == "calls" else [])

    class StorageMustNotRun:
        def delete_file(self, **_kwargs):
            raise AssertionError("audio deleted before transcription retry")

    monkeypatch.setattr(retention.aw, "storage", StorageMustNotRun)
    assert retention.cleanup_expired_audio() == {"deleted": 0, "skipped_active": 1}


def test_exhausted_transient_retry_resumes_after_cooldown(monkeypatch):
    saved = []
    monkeypatch.setattr(queue.repos, "get_doc", lambda *_: {
        "attempt_count": 5, "max_attempts": 6})
    monkeypatch.setattr(queue.repos, "update_doc", lambda *args: saved.append(args[-1]))
    queue.fail_job("job1", "network unavailable", retryable=True)
    assert saved[-1]["status"] == "QUEUED"
    assert saved[-1]["attempt_count"] == 0
    retry_at = datetime.fromisoformat(saved[-1]["next_attempt_at"])
    assert retry_at > datetime.now(UTC) + timedelta(minutes=29)
    queue.fail_job("job1", "unknown job type", retryable=False)
    assert saved[-1]["status"] == "FAILED"


def test_daily_batch_releases_at_1801_karachi():
    assert latest_processing_date(datetime(2026, 9, 26, 9, 34, tzinfo=PKT)).isoformat() == "2026-09-25"
    assert latest_processing_date(datetime(2026, 9, 26, 18, 0, tzinfo=PKT)).isoformat() == "2026-09-25"
    assert latest_processing_date(datetime(2026, 9, 26, 18, 1, tzinfo=PKT)).isoformat() == "2026-09-26"


def test_morning_restart_does_not_discover_today(monkeypatch):
    monkeypatch.setattr(runner.repos, "get_setting", lambda *_: "2026-09-25")
    monkeypatch.setattr(runner, "sync_date",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("early sync")))
    assert runner.scheduled_sync_window(datetime(2026, 9, 26, 9, 34, tzinfo=PKT)) == []


def test_first_morning_start_waits_for_evening(monkeypatch):
    monkeypatch.setattr(runner.repos, "get_setting", lambda *_: "")
    monkeypatch.setattr(runner, "newest_jazz_call", lambda: None)
    assert runner.scheduled_sync_window(datetime(2026, 9, 26, 9, 34, tzinfo=PKT)) == []


def test_evening_batch_includes_previous_after_hours_calls(monkeypatch):
    fetched = []
    markers = []
    monkeypatch.setattr(runner.repos, "get_setting", lambda *_: "2026-09-25")
    monkeypatch.setattr(runner, "newest_jazz_call", lambda: {"actual_started_at": "2026-09-26T05:00:00+00:00"})
    monkeypatch.setattr(runner, "discovery_dates", lambda *_: ["2026-09-26"])

    def sync(day, **kwargs):
        fetched.append((day, kwargs))
        return {"status": "SUCCESS"}

    monkeypatch.setattr(runner, "sync_date", sync)
    monkeypatch.setattr(runner.repos, "set_setting", lambda *args: markers.append(args))
    runner.scheduled_sync_window(datetime(2026, 9, 26, 18, 1, tzinfo=PKT))
    assert fetched == [
        ("2026-09-25", {"max_reporting_date": "2026-09-26", "min_reporting_date": "2026-09-26"}),
        ("2026-09-26", {"max_reporting_date": "2026-09-26", "min_reporting_date": None}),
    ]
    assert markers == [("last_scheduled_reporting_date", "2026-09-26")]


def test_worker_does_not_claim_current_day_jobs_before_1801(monkeypatch):
    queries_seen = []
    monkeypatch.setattr(queue, "_now", lambda: datetime(2026, 9, 26, 9, 34, tzinfo=PKT))
    monkeypatch.setattr(queue.repos, "list_docs",
                        lambda _table, queries, **_kwargs: queries_seen.append(queries) or [])
    assert queue.claim_next_job("worker1") is None
    assert queries_seen
    for queries in queries_seen:
        assert any('"reporting_date"' in q and '"2026-09-25"' in q for q in queries)
