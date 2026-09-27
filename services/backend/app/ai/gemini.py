"""Native Gemini REST requests, bounded failures and shared worker pacing.

No OpenAI compatibility shim, hidden model fallback, tracing, or request logging.
"""

from __future__ import annotations

import base64
import math
import re
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import httpx

from app.config.settings import get_settings

API = 'https://generativelanguage.googleapis.com/v1beta/models'
_lock = threading.Lock()
_pace_state = {"last": 0.0}
_budget = ContextVar("gemini_request_budget", default=None)


class GeminiError(RuntimeError):
    def __init__(self, message, *, status=0, retry_after=0):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after
        self.retryable = status in (0, 408, 429, 500, 502, 503, 504)
        self.code = 'GEMINI_RATE_LIMITED' if status == 429 else 'GEMINI_API_FAILED'


@contextmanager
def limited_requests(limit):
    budget = {"remaining": limit, "used": 0}
    token = _budget.set(budget)
    try:
        yield budget
    finally:
        _budget.reset(token)


def pace_request():
    """Worker leases serialize AI phases; persist spacing between child runtimes."""
    settings = get_settings()
    interval = 60 / settings.GEMINI_REQUESTS_PER_MINUTE
    with _lock:
        previous = _pace_state["last"]
        persistent = settings.GEMINI_DURABLE_RATE_LIMIT
        if persistent:
            from app.appwrite import repos
            previous = max(previous, float(repos.get_setting('gemini_last_request_at') or 0))
        now = time.time()
        if previous + interval > now:
            time.sleep(previous + interval - now)
        _pace_state["last"] = time.time()
        if persistent:
            repos.set_setting('gemini_last_request_at', str(_pace_state["last"]))


def generate(model, parts, *, system=None, schema=None, transcription=False):
    settings = get_settings()
    if not settings.GEMINI_API_KEY:
        raise GeminiError('GEMINI_API_KEY is not configured', status=401)
    model = model.removeprefix('models/')
    if not re.fullmatch(r'[a-zA-Z0-9._-]+', model):
        raise GeminiError('Invalid Gemini model identifier', status=400)
    payload = {'contents': [{'role': 'user', 'parts': parts}]}
    config = {}
    if transcription:
        config['audioTranscriptionConfig'] = {
            'mode': 'VERBATIM', 'diarization': True, 'wordTimestamp': True,
            'languageCodes': [],
        }
    else:
        config.update({'temperature': 0.1, 'maxOutputTokens': settings.GEMINI_MAX_OUTPUT_TOKENS})
        if schema:
            config['responseMimeType'] = 'application/json'
            config['responseJsonSchema'] = schema
        if system:
            payload['systemInstruction'] = {'parts': [{'text': system}]}
    payload['generationConfig'] = config
    budget = _budget.get()
    if budget is not None:
        if budget["remaining"] <= 0:
            raise GeminiError("Smoke test request budget exhausted", status=400)
        budget["remaining"] -= 1
        budget["used"] += 1
    pace_request()
    try:
        response = httpx.post(API + '/' + model + ':generateContent', json=payload,
                              headers={'x-goog-api-key': settings.GEMINI_API_KEY},
                              timeout=settings.GEMINI_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise GeminiError('Gemini network request failed (' + type(exc).__name__ + ')') from None
    if response.is_error:
        try:
            error = response.json().get('error', {})
        except ValueError:
            error = {}
        delay = 0.0
        for detail in error.get('details', []):
            retry = str(detail.get('retryDelay', '')).removesuffix('s')
            try:
                delay = max(delay, float(retry))
            except ValueError:
                pass
        try:
            delay = max(delay, float(response.headers.get('Retry-After', 0)))
        except ValueError:
            pass
        if response.status_code == 429:
            delay = max(delay, 60)
        message = str(error.get('message', 'Request rejected')).replace(settings.GEMINI_API_KEY, '[redacted]')[:1200]
        raise GeminiError(f'Gemini HTTP {response.status_code}: {message}',
                          status=response.status_code, retry_after=math.ceil(delay))
    try:
        data = response.json()
    except ValueError:
        raise GeminiError('Gemini returned invalid JSON', status=502) from None
    candidates = data.get('candidates', [])
    if not candidates:
        raise GeminiError('Gemini returned no candidate (blocked or empty response)', status=422)
    if candidates[0].get('finishReason') not in (None, 'STOP'):
        raise GeminiError('Gemini output was incomplete: ' + str(candidates[0]['finishReason']), status=502)
    return data


def output_parts(data):
    return data['candidates'][0].get('content', {}).get('parts', [])


def text_output(data):
    return ''.join(part.get('text', '') for part in output_parts(data) if not part.get('thought'))


def structured_output(instructions, model, output_type, user_content):
    response = generate(model, [{'text': user_content}], system=instructions,
                        schema=output_type.model_json_schema())
    return output_type.model_validate_json(text_output(response))


def _seconds(value):
    if isinstance(value, dict):
        return float(value.get('seconds', 0)) + float(value.get('nanos', 0)) / 1e9
    return float(str(value).removesuffix('s'))


def transcribe(path: Path):
    if path.stat().st_size > 14 * 1024 * 1024:
        raise GeminiError('Audio chunk exceeds safe inline upload size; use ten-minute normalized chunks', status=413)
    mime = {'.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4'}.get(path.suffix.lower())
    if not mime:
        raise GeminiError('Unsupported normalized audio format', status=415)
    data = generate(get_settings().GEMINI_TRANSCRIBE_MODEL, [{'inlineData': {
        'mimeType': mime, 'data': base64.b64encode(path.read_bytes()).decode()}}], transcription=True)
    return transcript_segments(data)


def transcript_segments(data):
    """Group word annotations into bounded turns without inventing diarization."""
    segments = []
    words = []
    for part in output_parts(data):
        annotation = part.get('audioTranscription')
        if not annotation:
            continue
        speaker = annotation.get('speakerLabel') or 'UNKNOWN'
        for word in annotation.get('words', []):
            text = word.get('word', '').strip()
            if not text:
                continue
            try:
                start, end = _seconds(word['startOffset']), _seconds(word['endOffset'])
            except (KeyError, TypeError, ValueError):
                raise GeminiError('Gemini word annotation is missing valid timestamps', status=422) from None
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
                raise GeminiError('Gemini returned invalid word timestamps', status=422)
            words.append((start, end, speaker, text))
    for start, end, speaker, text in sorted(words, key=lambda item: item[0]):
        if (segments and segments[-1]['speaker'] == speaker and start - segments[-1]['end'] <= 1.5
                and end - segments[-1]['start'] <= 20 and len(segments[-1]['text']) + len(text) < 3500):
            segments[-1]['text'] += ' ' + text
            segments[-1]['end'] = max(segments[-1]['end'], end)
        else:
            segments.append({'speaker': speaker, 'start': start, 'end': end, 'text': text})
    if not segments and text_output(data).strip():
        raise GeminiError('Speech returned without requested diarization/timestamps; refusing fabricated segments', status=422)
    return segments
