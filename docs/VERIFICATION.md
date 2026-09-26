# End-to-end verification

Verified against the live Jazz account and local Appwrite on 25–26 September 2026.
Credentials came from the existing environment and were not printed.

## Inherited defects corrected

- Jazz selectors and recording handling were assumptions; the inspector depended on human login and navigation.
- First-run/catch-up discovery did not follow the persisted source-call cursor correctly.
- The recording detail URL returned HTML, not audio. Appwrite upload calls did not match the installed SDK.
- WAV recordings were presented to transcription with an incorrect file extension; fallback response formats were incompatible.
- Agents SDK did not receive the environment key explicitly, and the grading output schema failed strict validation.
- Empty speech and calls with no applicable grading evidence caused repeated failures.
- Report completion, durable recovery, retention failures, and container packaging had gaps.
- The web app lacked the Tailwind PostCSS configuration, leaving the dashboard unstyled.

## Verified Jazz contract

- Home: `/Businessvpbx/admin/vpbxadmin`; authenticated marker: `#dropdownMenuLink`.
- Login: `/Businessvpbx/admin/user/loginvpbx`; inputs `name=diodid`, `name=password`, submit `name=submit`.
- Hierarchy: **VPBX Reports → Outbound CDRs / Inbound CDRs**.
- CDR routes: `/cdr_details_outbound` and `/cdr_details_inbound` under authenticated home.
- Date controls: `#startDate`, `#endDate`, hidden `#dtp_start_date`, `#dtp_end_date`.
- Table: `#table_cdr`. The portal's dated AJAX GET accepts `start_date` and `end_date` with `X-Requested-With: XMLHttpRequest`.
- DataTables pagination is client-side. The AJAX response contains all rows: 50 outbound rows appeared across five UI pages, and the adapter read all 50 plus eight inbound rows.
- `Client Number` is the remote customer in both tables; `Ext No` is the Jazz agent identifier. Observed raw statuses were `ANSWERED`, `NO ANSWER`, and `BUSY`.
- Hierarchy: **VPBX Manager → Extensions Details** (`/extension_details`, table `#example1`). Exact named entries resolved Saima to extension **1003** and Kiran to **1002**. Their linked mobile identifier, without the leading zero, matches CDR `Ext No`. Ambiguous/shared entries remain unassigned.
- Recording detail links end in `/callrecording/{id}`. The authenticated detail HTML exposes the WAV in `<audio><source src=...>`. The adapter downloads that source through the authenticated request context, validates media, hashes it, and uploads privately.
- Jazz reused one recording ID across multiple inbound routing legs. Dedupe therefore includes the source ID and stable row timestamp, direction, customer, agent, and duration.

## Automatic operation

Office hours are 09:30–18:00 Karachi. Today's batch starts at 18:01; a first morning startup waits for that release. It discovers the day's calls through 18:00. Later batches use the persisted source cursor and overlap, including the previous day's post-18:00 calls. Today's post-18:00 calls wait for tomorrow's batch. AI completion does not control discovery.

Startup recovers stale leases and incomplete checkpoints; today's jobs remain held until 18:01. Automatic login works from a fresh browser profile; expired sessions reauthenticate. Transient jobs use bounded retry bursts followed by a 30-minute automatic cooldown. Startup/hourly checks retry missed closed batches. The main sync runs at 18:01 Karachi and retention at 02:30 Karachi.

Reporting retains the existing after-18:00 assignment to the next reporting date. Empty dates receive a report entry. Audio expiry is the actual call timestamp plus 15 days; audio needed for a transcription retry is protected. Transcripts, grades, and reports remain after deletion.

## Live results for 2026-09-25

| Result | Count |
|---|---:|
| Total persisted calls | 58 |
| Outbound | 50 |
| Inbound | 8 |
| Answered (combined) | 19 |
| No answer (combined) | 37 |
| Busy | 2 |
| Private recordings uploaded | 19 |
| Structured grades completed | 17 |
| No speech | 1 |
| Ungradable; transcript retained | 1 |
| Remaining processing / failed jobs | 0 / 0 |

The outbound counts reconcile: **17 answered + 31 no answer + 2 busy = 50**.
Every persisted row had a remote customer number. A real stored recording passed ffprobe (89.9 seconds) and its SHA-256 matched the downloaded media.

Repeated same-date syncs discovered zero new calls, queued zero downloads, and kept the total at 58. Container startup and overnight scheduled syncs also discovered zero duplicates. The daily report is `COMPLETE`, with a real generated coaching summary. Backend readiness, dashboard, and report endpoints returned HTTP 200.

## Verification gates

- Backend: 32 tests pass; Ruff passes.
- Frontend: 15 Vitest tests pass; TypeScript and production builds pass.
- Sanitized tests cover verified Jazz columns/statuses/direction, shared source IDs, first run and cursor overlap, the 18:01 release, morning restart deferral, prior-day after-hours calls, resume after download, OpenAI outage, report waiting, silent/ungradable outcomes, retention failure, and transcription retry protection.
- Docker API/worker/scheduler/web images build; worker Chromium launches and Appwrite is reachable.
- Development and production Compose configurations validate.

## September 26 recovery and schedule verification

Docker Desktop stopped because the host disk was full. Mole cleaned 801.1 MB of user caches/logs; package and Docker build-cache cleanup recovered additional space. Personal files, Trash, Appwrite database/storage volumes, and Docker's disk image were preserved. The existing Appwrite stack was restarted without reinstalling it. Its 58 calls, 17 grades, completed September 25 report, and 81 completed jobs remained intact.

The updated scheduler and worker were deployed. At 09:54 Karachi, the verified next daily release was **September 26 at 18:01 +05:00**. The completed batch marker was September 25, the morning sync returned no work, and there were no queued or leased jobs. Today's batch therefore remains deferred until the requested evening release; after-18:00 calls belong to tomorrow's batch.

All four updated application images built successfully and are running. The dashboard's styled layout was verified in the browser after deployment. Readiness, dashboard, September 25/26 report pages, and the System page returned HTTP 200. After the final build-cache cleanup, the host retained approximately 5.2 GiB of free space.

## Exact files changed

Subsequent admin-authentication/Sites changes are documented in `docs/APPWRITE_SITES.md`. Protected web pages moved under `apps/web/app/(protected)/` without changing their public routes. New files include `lib/auth.ts`, `lib/auth.test.ts`, `lib/format.ts`, `app/(protected)/layout.tsx`, `app/api/auth/login/route.ts`, `app/api/auth/logout/route.ts`, `vitest.config.ts`, `services/backend/tests/test_api_auth.py`, and `scripts/prepare_appwrite_site.py`. The login form, root layout, backend fetch helper, audio proxy, web package/lockfile, environment example, Compose files, and deployment docs also changed.

Root/configuration:

- `.dockerignore`
- `.env.example`
- `README.md`
- `Makefile`
- `docker-compose.dev.yml`
- `docker-compose.prod.yml`

Documentation:

- `docs/JAZZ_AUTOMATION.md`
- `docs/LOCAL_SETUP.md`
- `docs/OPERATIONS.md`
- `docs/DEPLOYMENT.md`
- `docs/VERIFICATION.md`

Web/container:

- `apps/web/app/dashboard/page.tsx`
- `apps/web/app/calls/[id]/page.tsx`
- `apps/web/app/reports/[date]/page.tsx`
- `apps/web/app/system/page.tsx`
- `apps/web/pnpm-workspace.yaml`
- `apps/web/postcss.config.mjs`
- `infra/docker/Dockerfile.backend`
- `infra/docker/Dockerfile.worker`
- `infra/docker/Dockerfile.web`

Scripts:

- `scripts/jazz_inspect.py`
- `scripts/cli.py`
- `scripts/bootstrap_appwrite.py`

Backend:

- `services/backend/app/jazz/selectors.py`
- `services/backend/app/jazz/client.py`
- `services/backend/app/jazz/parser.py`
- `services/backend/app/jazz/exceptions.py`
- `services/backend/app/domain/helpers.py`
- `services/backend/app/domain/states.py`
- `services/backend/app/ingestion/runner.py`
- `services/backend/app/jobs/scheduler.py`
- `services/backend/app/jobs/worker.py`
- `services/backend/app/jobs/queue.py`
- `services/backend/app/appwrite/repos.py`
- `services/backend/app/transcription/service.py`
- `services/backend/app/ai/workflows.py`
- `services/backend/app/reporting/compute.py`
- `services/backend/app/retention/worker.py`
- `services/backend/app/config/settings.py`
- `services/backend/app/main.py`
- `services/backend/tests/test_jazz_integration.py`
# Deployment helper verification — September 26

Added `scripts/deploy_production.py` and the Appwrite runtime network Compose
overlay. Backend tests now total **42 passing**, including production-target
validation, refusal to overwrite secrets, malformed-config error redaction,
ambiguous-network rejection, scoped Site variable updates, and new/existing
recordings bucket access controls. Ruff passes.

Compose configuration and the deployment dry-run were checked with temporary
fake production values. The resolved configuration preserves special-character
credentials, owner-only environment-file permissions, the loopback-only API
host port, and the external runtime network alias. No real credentials were
used by these checks.

Production deployment, actual Site-runtime connectivity, and deployed Site
login/audio checks remain pending. Docker is currently stopped locally. The
helper performs readiness and network access checks when run on the VPS; these
are not claimed as completed production verification here.
