# Deployment (VPS)

Production Appwrite already runs on the VPS. Do NOT install another Appwrite, do NOT upgrade it.

## Deployment readiness

The autonomous pipeline and server-side Appwrite `admin` label authorization are verified locally. Pages, server actions, and the audio proxy are protected. Publish the repository to GitHub, then connect it through the production Appwrite Console's **Sites** feature with root directory `apps/web`, Next.js, and SSR. The API, worker, and scheduler remain in the existing production Docker environment. See [Appwrite Sites deployment](APPWRITE_SITES.md) for build settings, server variables, and verification steps. Production hosting is configured in the Console; the checked-in CLI configuration describes the linked local development project.

1. Copy repo, create `.env` with PRODUCTION values:
   `APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, `APPWRITE_API_KEY` (prod key),
   `OPENAI_API_KEY`, `JAZZ_UAN`, `JAZZ_PASSWORD`, `INTERNAL_API_TOKEN`,
   `BACKEND_INTERNAL_URL=http://backend-api:8000`, `NEXT_PUBLIC_*` → public URL values.
2. Build the backend images with `docker compose -f docker-compose.prod.yml build backend-api backend-worker`. Ensure `APPWRITE_ENDPOINT` is reachable from Docker containers, then run
   `docker compose -f docker-compose.prod.yml run --rm backend-api python /srv/scripts/bootstrap_appwrite.py`
   (schema-only, idempotent, data-safe).
3. `docker compose -f docker-compose.prod.yml up -d --no-build`.
4. Verify `GET /health/ready`, open web, check `/system`. Worker and scheduler
   use the Playwright image; their separate browser profiles share the state volume.
5. Expose the API through the existing HTTPS reverse proxy so Appwrite Sites can reach it. Require the internal API token; keep secrets server-side. Deploy Next.js using the Sites instructions above. Nightly Appwrite backup uses existing VPS tooling.

# Operations

- **Jazz down**: System page shows failed run + `JAZZ_*` code; the scheduler retries automatically on its next catch-up; queued AI jobs continue. Admin force-sync controls are optional.
- **OpenAI down**: jobs stay QUEUED with backoff and a 30-minute cooldown after each bounded retry burst; recordings stay safe and processing resumes automatically.
- **Retry a call**: System → failed job Retry; or `cli.py retry-failed`; per-call retranscribe/regrade endpoints.
- **Force a sync**: System “Sync Jazz now” or `cli.py sync-jazz --date YYYY-MM-DD`.
- **Inspect failures**: ingestion_runs + processing_jobs `last_error` + sanitized artifacts in `DEBUG_ARTIFACT_DIR` (7-day TTL).
- **Agent mappings**: Settings → Agents (audit logged; snapshots keep history).
- **Grading model**: `.env` `OPENAI_GRADING_MODEL` / `OPENAI_ROMANIZER_MODEL` (+ effort); version columns track what graded each call.
- **Retention**: `AUDIO_RETENTION_DAYS` (default 15) from the actual call timestamp; scheduler runs cleanup at 02:30 PKT and preserves audio still needed for transcription.
- **Regenerate report**: `POST /api/admin/reports/{date}/regenerate` or `cli.py regenerate-report`.
- **Backup**: Appwrite project backup (VPS) covers DB + bucket; keep `.env` in a vault, never in git.
- **Deploy new version**: rebuild images, `up -d`, watch `/health/ready` + `/system` backlog drain.
