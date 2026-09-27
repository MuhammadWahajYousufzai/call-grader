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

The new Gemini source has been tested on the host; it has not yet replaced the
local Appwrite Function deployments. Local native builds require more free disk
than currently available (about 4.5 GiB versus the documented 8 GiB build allowance).
A subsequent `deploy --local --paused` or production `deploy --paused` installs
the new source and secret variables without releasing the workload.
