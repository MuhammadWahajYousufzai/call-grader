# Deployment (VPS)

Production Appwrite already runs on the VPS. Do NOT install another Appwrite, do NOT upgrade it.

## Deployment readiness

The autonomous pipeline and server-side Appwrite `admin` label authorization are verified locally. Pages, server actions, and the audio proxy are protected. Publish the repository to GitHub, then connect it through the production Appwrite Console's **Sites** feature with root directory `apps/web`, Next.js, and SSR. The API, worker, and scheduler remain in the existing production Docker environment. See [Appwrite Sites deployment](APPWRITE_SITES.md) for build settings, server variables, and verification steps. Production hosting is configured in the Console; the checked-in CLI configuration describes the linked local development project.

Follow [production setup](PRODUCTION_SETUP.md) for the complete sequence:

1. Create the production Appwrite project and its server key.
2. Clone the repository on the same Docker host as Appwrite's executor.
3. Run `python3 scripts/deploy_production.py configure` to create a private
   `.env.production` file using production values and hidden credential input.
4. Run `python3 scripts/deploy_production.py deploy`. It builds the backend
   images, prepares the schema and private bucket, connects the API to the
   existing runtime network, starts the services, and checks backend access.
5. Connect GitHub in the production Appwrite Site and configure its three server
   variables. `configure-site` can set these through the authenticated CLI.
6. Redeploy the Site and verify admin login, System status, and audio.

This path uses `http://call-grader-api:8000` privately from the Site runtime and
does not require a public API domain. For a Site on another Docker host, expose
the API through the existing HTTPS reverse proxy instead and set the Site's
`BACKEND_INTERNAL_URL` to that URL. Nightly Appwrite backup uses existing VPS tooling.

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
