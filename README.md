# Yousuf Rice — Call Grader & Coaching AI

Internal web app that automatically reviews every customer call:

```
Jazz portal → deterministic Playwright → metadata + recording
→ Appwrite (calls + private audio + durable jobs)
→ OpenAI diarized transcription → Roman Urdu normalization
→ Call Grader (Agents SDK) → deterministic daily aggregation
→ Next.js dashboard
```

AI is used only for transcription/understanding/grading — never for clicking around Jazz.

## Prerequisites

- Docker (Appwrite 2.3.0 runs in `/Desktop/appwrite`)
- Python 3.12+ with `uv`, Node 22+ with `pnpm`, `ffmpeg`
- OpenAI API key, Jazz UAN/password, local Appwrite project + API key

## Run Functions + Sites locally

With the Appwrite CLI logged in and this development project linked, use:

```sh
uv run --project services/backend python scripts/deploy_appwrite.py configure --local
uv run --project services/backend python scripts/deploy_appwrite.py deploy --local
```

This uses the existing private `.env`, deploys Functions and the Next.js Site,
verifies native tools, and enables Appwrite schedules. Open the generated Site
URL under `sites.localhost`. Give your project account the exact `admin` label.
See [Functions setup](docs/APPWRITE_FUNCTIONS.md) for runtime prerequisites.

The following numbered setup steps describe the Docker/developer alternative.

## 1. Local Appwrite 2.3 setup

Appwrite is already running at `http://localhost/v1` (see `docker ps` in `/Desktop/appwrite/appwrite`).
Create/get a project + API key (scopes: databases, storage, users read):

```bash
appwrite whoami
appwrite list-projects   # -> project id, e.g. 6ab64644002bdf0b5ed2
```

In the Appwrite Console (`http://localhost`), create an API key for that project and copy it.

## 2. .env setup

```bash
cp .env.example .env
# fill: APPWRITE_PROJECT_ID, APPWRITE_API_KEY,
#       OPENAI_API_KEY, JAZZ_UAN, JAZZ_PASSWORD, INTERNAL_API_TOKEN (random string)
```

No `NEXT_PUBLIC_*` secret may ever hold a server key. Only endpoint + project id are public.

## 3. Appwrite bootstrap (idempotent, never destroys data)

```bash
cd services/backend && uv sync
uv run python ../../scripts/bootstrap_appwrite.py
```

Creates database `call_grader`, 10 tables + indexes, private `call_recordings` bucket,
seeds agents (Saima/Kiran) and default business rules.

## 4. Automatic Jazz ingestion

Set `JAZZ_UAN` and `JAZZ_PASSWORD` in `.env`, then start the worker and scheduler.
Playwright logs in, discovers the dated inbound and outbound CDRs, and downloads
eligible recordings automatically. Office hours are 09:30–18:00 Karachi; each
day's batch starts at 18:01. A first morning start waits until 18:01, then ingests
the day's calls through 18:00. Later runs resume from the newest persisted Jazz
call with overlap and include the previous day's calls after 18:00. Startup
catch-up retries missed closed batches. `sync-jazz` is an optional admin command;
the worker holds today's queued jobs until the 18:01 release.

## 5. Running all services (4 terminals)

```bash
make api        # FastAPI :8000
make worker     # pipeline worker (Playwright + AI)
make scheduler  # 18:01 PKT sync + catch-up + retention
pnpm --dir apps/web dev   # Next.js :3000
```

Or `docker compose -f docker-compose.dev.yml up --build`.

## 6. Tests

Dashboard access requires an Appwrite project account with the server-managed
`admin` label. Production frontend hosting uses **Appwrite Sites (Next.js SSR)**;
see [authentication and Sites deployment](docs/APPWRITE_SITES.md).

```bash
cd services/backend && uv run pytest -q
pnpm --dir apps/web test
```

## 7. Production deployment — Appwrite Functions + Sites

Use the existing production Appwrite project for the backend Functions, native
schedules, database, recordings, account authentication, and Next.js Site.
See [Functions + Sites setup](docs/APPWRITE_FUNCTIONS.md) for the automatic
Appwrite CLI deployment helper and GitHub Console settings.

```sh
python3 scripts/deploy_appwrite.py configure --project-id YOUR_PRODUCTION_PROJECT_ID
python3 scripts/deploy_appwrite.py deploy
```

Discovery starts daily at 18:01 Karachi; Appwrite cron executions recover missed
runs and queued processing. The Site calls the private API Function through the
Server SDK. No additional backend reverse proxy is needed. The Docker helpers
remain available for local development and an optional deployment fallback.

## 8. Troubleshooting

- `JAZZ_PAGE_CHANGED` on System page → inspect the portal change with the optional
  `jazz_inspect.py` diagnostic and update the adapter after verification.
- Backlog growing → check OpenAI key/quota on System page; recordings stay safe and retry automatically.
- Audio 404 after 15 days → expected: transcript/grade/report retained, raw audio deleted.
- See `docs/OPERATIONS.md` for retry/regen/backup procedures.
