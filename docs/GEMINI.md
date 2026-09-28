# Gemini models and bounded testing

The pipeline uses the selected models through the native Gemini REST API:

| Phase | Environment variable | Selected model |
| --- | --- | --- |
| Verbatim audio, diarization, word timestamps | `GEMINI_TRANSCRIBE_MODEL` | `gemini-3.5-transcribe` |
| Roman Urdu normalization | `GEMINI_ROMANIZER_MODEL` | `gemini-3.8-flash` |
| Grading and daily coaching | `GEMINI_GRADING_MODEL` | `gemini-3.8-flash` |

`GEMINI_API_KEY` belongs only in private environment/configuration files and the
Worker Function's secret variables. No OpenAI SDK, compatibility adapter, tracing,
or fallback model is used. Transcription auto-detects speech languages. Product
hints are deliberately omitted from the audio request because custom vocabulary
cannot be combined with native diarization/timestamps. Speaker role assignment
still uses the application's heuristics and uncertainty flags; speaker labels do
not prove which speaker is the agent. Human review should check these assignments.

## Request pacing and failures

`GEMINI_REQUESTS_PER_MINUTE=2` is our conservative application cap, **not a claim
about Google's quota**. A durable Appwrite setting spaces requests across Worker
Function executions, which share the existing global Worker lease. The free tier
also has daily/token limits. HTTP 429 and transient 5xx failures remain queued with
backoff; provider retry delays take precedence when longer. Permanent permission
or model errors fail visibly. There are no immediate hidden retries.

Check your actual active limits in Google AI Studio. Google applies limits to the
project, rather than each key. Enable billing on the intended Gemini project to
use paid quota; merely swapping keys does not establish that billing is active.
Paid billing also does not guarantee relief from temporary model demand errors.
See [Google rate limits](https://ai.google.dev/gemini-api/docs/rate-limits) and
[pricing/data use](https://ai.google.dev/gemini-api/docs/pricing).

## One-recording smoke test

Keep discovery/catch-up/worker/maintenance disabled while testing. The helper reads
one existing private recording, caps audio at 180 seconds, and makes at most four
generation requests per invocation (transcription, Roman Urdu, grading, coaching).
No calls, grades, reports or queue rows are changed; only the pacing setting is
updated. Private checkpoint/report files are excluded from Git.

```sh
uv run --project services/backend python scripts/smoke_gemini.py \
  --call-id YOUR_RETAINED_CALL_ID --output .verification/gemini-smoke.json
```

Reusing the same path resumes only incomplete phases, without re-transcribing.
A different model/recording invalidates the checkpoint; choose a new output path.
The report states incomplete results and preserves real speaker timing. Grading
scores are computed deterministically from validated dimension scores.

## September 27 test evidence

Both selected model IDs were available in the key's live model catalogue.
One retained 59.04-second recording was tested twice, consuming four generation
requests total: two successful native transcriptions and two failed Roman Urdu
requests. Each transcription returned 16 turns with two speaker labels and real
word timestamps. Both Flash requests returned HTTP 503/high demand. Further calls
were stopped. Roman Urdu, grading and coaching are therefore **not yet verified**.
The second transcription is checkpointed for the next bounded retry. Existing
call results were preserved, and all four workload Functions remain disabled
with their schedules cleared. API and bootstrap remain available.

### September 28 bounded alternative-model check

The key's live catalogue lists both `gemini-3.5-flash` and `gemini-2.5-flash`.
We used `gemini-2.5-flash` for Roman Urdu, grading and coaching on the saved
59.04-second, 16-turn transcript. All three phases succeeded without another
audio transcription. The resulting score was 8.8/10. This is a functional model
check; the grader itself flagged incorrect speaker attribution in segments 10–13.
The score should not be treated as verified until a human checks roles, transcript
words and grading against the recording. The test used repository bootstrap business rules, which
were confirmed identical to the five current local Appwrite rules. Local Appwrite
was unavailable during the API calls, so the test used cached transcript and
known outbound call metadata; it did not write call rows.

The default `.env` model choices remain unchanged. The private test checkpoint and
report record the alternate model. The deployment helper accepts `--flash-model`
to target this model for a paused local build without changing `.env` or the
private production configuration.


## Local deployment verification

The Gemini Functions and Next.js Site were rebuilt in the local Appwrite project
with `deploy --local --paused --flash-model gemini-2.5-flash`. All six Function
builds, native Chromium/FFmpeg/audio checks, private scopes, ten tables, storage,
Site build and API readiness passed. The Worker has the 2.5 Flash model override
through server-side variables. Sync, catch-up, Worker and maintenance Functions
remain disabled with empty schedules; no full workload was released.

Browser verification passed anonymous and non-admin denial, admin access to
Dashboard/System and private audio, and immediate denial after replacing the admin
label. The temporary account was deleted. A disposable first-install schema test
exposed unbounded TEXT columns on indexed fields; bootstrap now creates bounded
VARCHAR columns there. The rerun passed ten tables, indexes, bucket creation and
repeat-safe seeds, then removed all disposable resources. The corrected bootstrap
Function was activated with read-only scope.
