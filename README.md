# Yousuf Rice — Call Grader & Coaching AI

Autonomous call review: Jazz discovery → private recordings → transcription →
Roman Urdu → AI grading/coaching → daily dashboard. The owner reviews results.

## Deployment

**Appwrite Functions + Appwrite Sites in one project.** Appwrite provides
schedules, accounts, database, private storage and hosting. No separate API,
worker or scheduler containers are deployed by this repository.

- [Production checklist and commands](docs/PRODUCTION_SETUP.md)
- [Functions, schedules and GitHub settings](docs/APPWRITE_FUNCTIONS.md)
- [Local setup](docs/LOCAL_SETUP.md)
- [Authentication and Sites](docs/APPWRITE_SITES.md)
- [Gemini configuration and bounded testing](docs/GEMINI.md)
- [Verification evidence](docs/VERIFICATION.md)

Office hours are 09:30–18:00 Karachi. Discovery starts daily at **18:01**;
calls after 18:00 join the following day's batch. Appwrite watchdogs retry
missed discovery, interrupted jobs and expired leases automatically.

## Local Functions + Sites

Keep the existing local Appwrite running, log into its CLI and use the linked
project. Configure the private `.env` using `.env.example` if needed.

```sh
uv run --project services/backend python scripts/deploy_appwrite.py configure --local
make deploy-local
make verify-local
```

If `.env.appwrite-local.json` already exists, skip `configure`. Open the generated
Site under `sites.localhost`; only an account with the exact `admin` label has
access. Appwrite itself uses Docker; this repository has no Docker app deployment.

## Tests

```sh
make test
make lint
pnpm --dir apps/web exec tsc --noEmit
pnpm --dir apps/web build
```

## Operations

The System page shows discovery, retry/backlog and scheduling state. Gemini
uses the configured models; exhausted quota leaves durable jobs queued with
backoff. Real recordings remain private. Audio is deleted after 15 days once
transcription no longer needs it; transcripts, grades and reports are retained.
See [operations](docs/OPERATIONS.md).
