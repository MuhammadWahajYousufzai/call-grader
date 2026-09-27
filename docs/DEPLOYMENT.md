# Production deployment

Deploy the backend to Appwrite Functions and the Next.js frontend to Appwrite
Sites in one project on the existing production instance. Follow
[Functions + Sites setup](APPWRITE_FUNCTIONS.md). The deployment helper sets
variables, provisions private data resources, verifies the native runtime, and
then enables Appwrite schedules. Production Appwrite is not reinstalled.

The existing Docker path is an optional fallback documented in
[PRODUCTION_SETUP.md](PRODUCTION_SETUP.md).

# Operations

- **Jazz down**: System page shows failed run + `JAZZ_*` code; Appwrite retries automatically on its next catch-up; queued AI jobs continue. Admin force-sync controls are optional.
- **OpenAI down**: jobs stay QUEUED with backoff and a 30-minute cooldown after each bounded retry burst; recordings stay safe and processing resumes automatically.
- **Retry a call**: System → failed job Retry; or `cli.py retry-failed`; per-call retranscribe/regrade endpoints.
- **Force a sync**: System “Sync Jazz now” or `cli.py sync-jazz --date YYYY-MM-DD`.
- **Inspect failures**: ingestion_runs + processing_jobs `last_error` + sanitized artifacts in `DEBUG_ARTIFACT_DIR` (7-day TTL).
- **Agent mappings**: Settings → Agents (audit logged; snapshots keep history).
- **Grading model**: worker Function variables `OPENAI_GRADING_MODEL` / `OPENAI_ROMANIZER_MODEL` (+ effort); version columns track what graded each call.
- **Retention**: `AUDIO_RETENTION_DAYS` (default 15) from the actual call timestamp; the maintenance Function runs cleanup at 02:30 PKT and preserves audio still needed for transcription.
- **Regenerate report**: `POST /api/admin/reports/{date}/regenerate` or `cli.py regenerate-report`.
- **Backup**: Appwrite project backup (VPS) covers DB + bucket; keep `.env` in a vault, never in git.
- **Deploy new version**: push GitHub-connected Functions/Site or rerun the Appwrite helper; verify builds, executions, and `/system` backlog.
