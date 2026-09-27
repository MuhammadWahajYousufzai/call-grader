"""Native provider contract, quota safety, and transcript integrity."""
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from app.ai import gemini
from app.config.settings import Settings


@pytest.fixture
def provider(monkeypatch):
    settings = SimpleNamespace(GEMINI_API_KEY='private-test-key', GEMINI_TIMEOUT_SECONDS=120,
                               GEMINI_MAX_OUTPUT_TOKENS=16384, GEMINI_REQUESTS_PER_MINUTE=2,
                               GEMINI_DURABLE_RATE_LIMIT=False)
    monkeypatch.setattr(gemini, 'get_settings', lambda: settings)
    monkeypatch.setattr(gemini, 'pace_request', Mock())
    return settings


def success(parts):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': parts}}]}


def test_transcription_uses_native_selected_model_without_text_prompt(provider, monkeypatch):
    post = Mock(return_value=httpx.Response(200, json=success([])))
    monkeypatch.setattr(gemini.httpx, 'post', post)
    gemini.generate('gemini-3.5-transcribe', [{'inlineData': {'mimeType': 'audio/mpeg', 'data': 'YQ=='}}], transcription=True)
    args, kw = post.call_args
    assert args[0].endswith('/gemini-3.5-transcribe:generateContent')
    assert 'private-test-key' not in args[0]
    assert kw['headers'] == {'x-goog-api-key': 'private-test-key'}
    assert kw['json']['generationConfig'] == {'audioTranscriptionConfig': {
        'mode': 'VERBATIM', 'diarization': True, 'wordTimestamp': True, 'languageCodes': []}}
    assert 'systemInstruction' not in kw['json']


@pytest.mark.parametrize('status,retryable', [(429, True), (503, True), (403, False), (400, False)])
def test_errors_are_sanitized_and_quota_delay_is_preserved(provider, monkeypatch, status, retryable):
    post = Mock(return_value=httpx.Response(status, headers={'Retry-After': '90'}, json={'error': {
        'message': 'private-test-key rejected', 'details': [{'retryDelay': '120.5s'}]}}))
    monkeypatch.setattr(gemini.httpx, 'post', post)
    with pytest.raises(gemini.GeminiError) as caught:
        gemini.generate('gemini-3.8-flash', [{'text': 'test'}])
    assert caught.value.retryable is retryable
    assert caught.value.retry_after == 121
    assert 'private-test-key' not in str(caught.value)
    assert post.call_count == 1  # No automatic workload bursts or provider fallback.


def test_smoke_request_budget_counts_failed_requests(provider, monkeypatch):
    post = Mock(return_value=httpx.Response(503, json={'error': {'message': 'busy'}}))
    monkeypatch.setattr(gemini.httpx, 'post', post)
    with gemini.limited_requests(1) as budget:
        with pytest.raises(gemini.GeminiError):
            gemini.generate('gemini-3.8-flash', [])
        with pytest.raises(gemini.GeminiError, match='budget exhausted'):
            gemini.generate('gemini-3.8-flash', [])
    assert budget['used'] == post.call_count == 1


def annotation(speaker, text, start, end):
    return {'audioTranscription': {'speakerLabel': speaker, 'words': [
        {'word': text, 'startOffset': str(start)+'s', 'endOffset': str(end)+'s'}]}}


def test_speaker_grouped_annotations_are_ordered_by_real_timestamps():
    data = success([annotation('a', 'one', 0, .5), annotation('a', 'three', 2, 2.5),
                    annotation('b', 'two', 1, 1.5)])
    assert [(s['speaker'], s['text'], s['start']) for s in gemini.transcript_segments(data)] == [
        ('a', 'one', 0), ('b', 'two', 1), ('a', 'three', 2)]


@pytest.mark.parametrize('start,end', [(-1, 1), (2, 1), ('nan', 3)])
def test_invalid_word_times_do_not_become_fabricated_segments(start, end):
    with pytest.raises(gemini.GeminiError, match='invalid word timestamps'):
        gemini.transcript_segments(success([annotation('a', 'speech', start, end)]))


def test_missing_annotations_fail_closed_but_silence_is_empty():
    with pytest.raises(gemini.GeminiError, match='without requested diarization'):
        gemini.transcript_segments(success([{'text': 'speech without times'}]))
    assert gemini.transcript_segments(success([])) == []


def test_durable_pacing_survives_new_runtime(monkeypatch):
    settings = SimpleNamespace(GEMINI_REQUESTS_PER_MINUTE=2, GEMINI_DURABLE_RATE_LIMIT=True)
    monkeypatch.setattr(gemini, 'get_settings', lambda: settings)
    from app.appwrite import repos
    monkeypatch.setattr(repos, 'get_setting', lambda _: '990')
    persist = Mock()
    monkeypatch.setattr(repos, 'set_setting', persist)
    monkeypatch.setattr(gemini, '_pace_state', {'last': 0})
    monkeypatch.setattr(gemini.time, 'time', Mock(side_effect=[1000, 1020]))
    sleep = Mock()
    monkeypatch.setattr(gemini.time, 'sleep', sleep)
    gemini.pace_request()
    sleep.assert_called_once_with(20)
    persist.assert_called_once_with('gemini_last_request_at', '1020')


def test_job_backoff_honors_provider_retry_delay(monkeypatch):
    from app.jobs import queue
    monkeypatch.setattr(queue.repos, 'get_doc', lambda *a: {'attempt_count': 0, 'max_attempts': 6})
    patch = Mock()
    monkeypatch.setattr(queue.repos, 'update_doc', patch)
    now = datetime(2026, 9, 27, tzinfo=UTC)
    monkeypatch.setattr(queue, '_now', lambda: now)
    assert queue.fail_job('job', 'rate limited', retry_after=600) == 'QUEUED'
    due = datetime.fromisoformat(patch.call_args.args[2]['next_attempt_at'])
    assert (due-now).total_seconds() == 600


@pytest.mark.parametrize('rate', [0, -1, float('nan'), float('inf')])
def test_invalid_pacing_is_rejected(rate):
    with pytest.raises(ValueError):
        Settings(_env_file=None, GEMINI_REQUESTS_PER_MINUTE=rate)
