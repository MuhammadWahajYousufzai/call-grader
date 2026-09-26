# Architecture

```
Jazz Business Line portal
        ↓  deterministic Playwright (app/jazz) — no LLM navigation
Call metadata + recording download (verified, checksummed)
        ↓
Appwrite: calls row (checkpoint) + private Storage audio + processing_jobs lease queue
        ↓
Worker: DOWNLOAD → TRANSCRIBE → ROMANIZE → GRADE  (each step checkpoints; resume at failed step)
        ↓
OpenAI diarized transcription (direct Audio API, gpt-4o-transcribe-diarize)
        ↓
Roman Urdu normalization (Agents SDK, gpt-6-luna)
        ↓
Call Grader (Agents SDK, gpt-6-sol) → Pydantic-validated grade; app computes weighted score
        ↓
Appwrite: transcript_segments + call_grades + daily_reports (deterministic aggregation)
        ↓
Next.js BFF → owner dashboard (Appwrite Auth, private audio proxy)
```

## Failure boundaries (independent by design)

- Jazz down ≠ OpenAI pipeline broken (queued jobs keep processing).
- OpenAI down ≠ Jazz downloader broken (recordings stay safe, jobs retry with backoff).
- Next.js offline ≠ ingestion stopped (workers/scheduler are separate processes).
- Worker restart ≠ progress lost (per-call checkpoint + `RESUME_FROM` map + job leases with stale recovery).

## Key invariants

- Dedupe by `dedupe_key` (unique index); same Jazz row never transcribed/graded twice.
- Scores: LLM returns dimension assessments; `weighted_score()` in app code computes 1–10.
- Metrics: `compute_report()` counts deterministically; LLM only writes qualitative coaching themes.
- Audio: private bucket, 15-day `recording_retention_due_at`, race-safe deletion; deletion never re-downloads (dedupe row persists).
- Secrets: Jazz/OpenAI/Appwrite keys server-side only; browser gets endpoint + project id.
