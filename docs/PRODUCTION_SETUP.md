# Production setup — Appwrite Functions + Sites

Use the existing Appwrite at `https://yousufricemill.com`. Create the production
project when deploying. Keep its current installation and data volumes.

## 1. Server prerequisites

- Functions and Sites enabled; Python `python-3.12` and Site Node 22 available.
- `_APP_FUNCTIONS_TIMEOUT` permits 900 seconds.
- Native builds can download Alpine/Python packages; sufficient build disk/RAM.
- Existing Appwrite hosting DNS/TLS configured for Site domains.
- Funded OpenAI API account and working Jazz credentials.

The helper checks available Python runtimes and rejects failed builds, missing
schema, unsafe resource permissions, invalid role scopes and unreadable Appwrite.

## 2. Create project and deploy from this repository

Create the production project in Console, then run:

```sh
appwrite login --endpoint https://yousufricemill.com/v1
python3 scripts/deploy_appwrite.py configure --project-id YOUR_PRODUCTION_PROJECT_ID
python3 scripts/deploy_appwrite.py deploy
```

Hidden prompts collect Jazz/OpenAI credentials. The helper generates the internal
token and stores `.env.appwrite-production.json` with mode 600 (ignored by Git).
No permanent Appwrite application API key is needed. Do not overwrite the linked
local manifest: the helper explicitly targets production using a temporary manifest.

Deployment creates six private Functions and one Next.js SSR Site, installs their
variables/scopes, provisions ten private tables/indexes and the recording bucket,
seeds settings/rules/agents, checks native tools and API access, builds the Site,
then enables schedules. Existing call data is preserved. If provisioning or a
build/check fails before schedules are enabled, fix the reported error and rerun
`deploy`; schema creation is idempotent. API/bootstrap have no schedule. Bootstrap
write scopes are removed after setup.

The helper automatically runs resource/runtime verification after deploying.
A first daytime deployment waits until 18:01 Karachi; later deployments catch up
missed closed batches. No manual Jazz login, recording download or grading is needed.

## 3. Account, domain and GitHub

Create your project account under **Auth → Users** and assign the exact `admin`
label. Choose the Site domain, for example `calls.yousufricemill.com`, and configure
its DNS/TLS with the existing Appwrite hosting setup.

Connect GitHub repository `MuhammadWahajYousufzai/call-grader`, branch `main`,
through Appwrite Console. Use root `apps/web` for the Site and root `.` for each
Function. Exact entrypoints/build commands/scopes are in
[APPWRITE_FUNCTIONS.md](APPWRITE_FUNCTIONS.md#github-deployments-through-console).
The helper installs all required variables. Preserve these settings for GitHub
builds. There is no public backend address or extra reverse proxy to configure:
the Site uses private Appwrite SDK Function executions.

## 4. Repeatable verification

```sh
python3 scripts/deploy_appwrite.py verify
uv run --project services/backend python scripts/deploy_appwrite.py verify --site-url https://calls.yousufricemill.com
```

The first command verifies active builds, private permissions, exact schedules,
role scopes, variables, all schema/indexes, bucket, API readiness and native tools.
The second also uses Chromium and creates a temporary project account to test
anonymous/non-admin denial, admin login, Dashboard/System and immediate denial
when its admin label is revoked. It deletes that account afterward. It verifies
private audio playback when a real recording exists; a new empty project reports
that playback check as skipped. Install Chromium for this optional browser check:
`uv run --project services/backend playwright install chromium`.

These verification commands do not call Jazz or OpenAI. Check the first scheduled
batch on Dashboard/System to verify production credentials, provider quota and
real AI results. System failures/backlog must not be mistaken for finished grades.

## Updates and recovery

Push GitHub-connected resources for source updates, or rerun the deployment helper
for resource/variable/schema changes. Rerun verification afterward. Appwrite cron
runs recover ordinary crashes automatically from durable jobs and checkpoints.
Back up Appwrite's database/bucket and store private config in a vault.
