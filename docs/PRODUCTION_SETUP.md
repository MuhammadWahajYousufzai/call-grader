# Production setup — existing Appwrite 2.3

The production Appwrite installation is already running at
`https://yousufricemill.com/v1`. This procedure adds one project containing six
Functions, one Next.js Site, ten private tables and the recording bucket. It does
not install Appwrite or deploy separate Docker application containers.

## 1. Prepare the project and server

In the Appwrite Console at `https://yousufricemill.com`, create a production
project and copy its **project ID**. The project is separate from the linked local
development project in `appwrite.config.json`. Confirm that Functions and Sites
are enabled, `python-3.12` and Site `node-22` are available, Function timeouts
allow 900 seconds, and native builds have internet access and enough disk/RAM.
Keep the existing Appwrite installation and volumes.
For automatic Git deployments later, configure the existing self-hosted
Appwrite GitHub integration and grant its installation access to this private
repository. The initial CLI deployment works without a GitHub integration.

Use a funded Gemini API project with quota for the selected models, plus working
Jazz credentials. The Worker will use `gemini-3.5-transcribe` for audio and
`gemini-3.8-flash` for Roman Urdu, grading and coaching. The earlier
`gemini-2.5-flash` run only checked the flow; it is not the production choice.

## 2. Deploy from the GitHub repository with Appwrite CLI

On the computer with the Appwrite CLI and `uv`, clone or update the repository,
then run these commands **from its root**. Replace the placeholder with the
project ID copied from the production Console:

```sh
git clone https://github.com/MuhammadWahajYousufzai/call-grader.git
cd call-grader
appwrite login --endpoint https://yousufricemill.com/v1
uv run --project services/backend python scripts/deploy_appwrite.py configure --project-id YOUR_PRODUCTION_PROJECT_ID
uv run --project services/backend python scripts/deploy_appwrite.py deploy --paused
uv run --project services/backend python scripts/deploy_appwrite.py verify --paused
```

If the repository is already cloned, use `git pull --ff-only` in its root instead
of cloning again. `configure` uses hidden prompts for the Gemini key and Jazz
credentials, generates the internal token, and creates
`.env.appwrite-production.json` with owner-only permissions. This ignored file
is the deployment target and secret source. Store a secure backup of it; later
runs reuse it. No permanent Appwrite application API key is needed. The helper
uses a temporary manifest targeting the production project, so it does not
relink or push the local `appwrite.config.json`.

The helper prints each Function build, schema/bootstrap check, native runtime
check, API readiness check, Site build, and final verification. `--paused`
keeps discovery, catch-up, Worker and maintenance disabled with empty schedules;
no Jazz or Gemini workload starts. It preserves existing data and is safe to
rerun after correcting a reported failure. API and bootstrap have no schedules.
The bootstrap Function's broad scopes are removed after provisioning.

## 3. Watch the deployment in CLI and Console

From the repository root, set the target in the terminal used for inspection.
These environment values override the checked-in local project manifest without
editing it. The read-only commands then show production deployment state. Run
them after the helper creates the resources, or from a second terminal while it
builds:

```sh
export APPWRITE_ENDPOINT=https://yousufricemill.com/v1
export APPWRITE_PROJECT_ID=YOUR_PRODUCTION_PROJECT_ID
appwrite functions list-deployments --function-id call-grader-worker --limit 5
appwrite sites list-deployments --site-id call-grader-web --limit 5
appwrite functions list-executions --function-id call-grader-bootstrap --limit 5
```

In the production Console, open **Functions → call-grader-worker → Deployments**
for build status and **Executions** for runtime results. Check the other five
Functions too. Open **Sites → call-grader-web → Deployments** for the SSR build,
and **Databases/Storage** for the private tables and bucket. A deployment must
reach `ready`; the helper's `PASS` checks confirm the active builds, scopes,
variables, schema, bucket, API and paused schedules. The Console may require a
refresh while a CLI build is running.

## 4. Connect GitHub, domain and admin access

The CLI deployment creates the Site and Functions from the checked-out GitHub
source. To enable future GitHub-triggered builds, connect **the existing Site**
and each existing Function to `MuhammadWahajYousufzai/call-grader`, branch
`main`, in the production Console. Use `apps/web` as the Site root and `.` as
each Function root. Preserve the build settings, schedules, scopes and private
variables installed by the helper; exact settings are in
[Functions deployment](APPWRITE_FUNCTIONS.md#github-deployments-through-console)
and [Sites/authentication](APPWRITE_SITES.md). Do not create a second Site or
Function with the same purpose.

Assign the exact server-managed `admin` label to your project account under
**Auth → Users**. Add an HTTPS Site domain, for example
`calls.yousufricemill.com`, using the existing Appwrite DNS/TLS setup. No
separate public backend domain is required: the Site calls the private API
Function through the Appwrite SDK. The Appwrite host handles HTTPS routing.

After the domain is live, run the optional browser check. It creates and deletes
a temporary account, checks anonymous and non-admin denial, admin access and
immediate label revocation. If a recording exists, it checks private playback.

```sh
uv run --project services/backend playwright install chromium
uv run --project services/backend python scripts/deploy_appwrite.py verify --paused --site-url https://calls.yousufricemill.com
```

## 5. Start the daily workload when quota is ready

The selected model names are in `.env.appwrite-production.json`. Confirm they
remain `gemini-3.5-transcribe` and `gemini-3.8-flash`, and that the configured
Gemini project has paid quota. Then run:

```sh
uv run --project services/backend python scripts/deploy_appwrite.py deploy
uv run --project services/backend python scripts/deploy_appwrite.py verify
appwrite functions list-executions --function-id call-grader-worker --limit 5
```

This enables Appwrite's native schedules and starts the initial sync/Worker
catch-up. Discovery runs daily at **18:01 Karachi**; calls after 18:00 join the
following day's batch. Check **System** and **Dashboard** for queue progress and
review real transcripts, speaker roles and grades. A successful build and
runtime check do not prove AI grading quality; the bounded test found speaker
attribution needing review in segments 10–13. Provider 429/5xx responses remain
visible and retry through durable jobs. See [Gemini testing](GEMINI.md) and
[operations](OPERATIONS.md).

For code updates, push `main` to GitHub and inspect the connected resource
builds in Console, or rerun the helper to apply code, variables and schema
changes together. Run verification afterward. Keep the production private
configuration out of Git and back up Appwrite's database and recording bucket.

Appwrite references: [Functions from Git](https://appwrite.io/docs/products/functions/deploy-from-git),
[Sites from Git](https://appwrite.io/docs/products/sites/deploy-from-git), and
[self-hosted compute settings](https://appwrite.io/docs/advanced/self-hosting/configuration/environment-variables).
