> Optional Docker fallback. The selected production path is
> [Appwrite Functions + Sites](APPWRITE_FUNCTIONS.md).

# Production setup beside your existing Appwrite

## What runs where

Use one production Appwrite project for authentication, the database, recordings,
and the Next.js Site. Run this project's API, worker, and scheduler as Docker
containers on the **same Docker host** as Appwrite's executor.

The deployment helper connects the API to Appwrite's existing runtime network.
The Site's server can then reach `http://call-grader-api:8000`. The browser talks
only to your HTTPS Site. The server checks the Appwrite account's current `admin`
label before contacting the API with a shared secret.

```text
Browser → HTTPS Appwrite Site → private Docker API → Appwrite project
                                  ↑
                          worker + scheduler
                           Jazz and OpenAI
```

No additional public API hostname or reverse proxy is needed for this path.
Appwrite's existing proxy continues serving its Console and Sites. A reverse
proxy is simply the server that receives a public HTTPS request and forwards it
to the correct internal service. If Sites runs on another host, this private
network path will not work; that setup needs a reachable HTTPS API URL instead.

## 1. Create the production project

In `https://yousufricemill.com`, create the project and copy its project ID.
Create a server API key with read/write access for the database, tables, columns,
indexes, rows, storage buckets, and files. This key stays on the VPS. Bootstrap
needs schema and bucket write access; the pipeline needs rows and files access.

Create the reviewer's **project user account**, then give that account the exact
`admin` label in the Console. A Console administrator login is separate from an
application account. No public sign-up or browser role editing is provided.

## 2. Configure the backend on the VPS

Requirements: existing Docker Engine and Compose, Python 3, Git, and a running
Appwrite executor. The scripts do not install, upgrade, or restart Appwrite.

```bash
git clone https://github.com/MuhammadWahajYousufzai/call-grader.git
cd call-grader
python3 scripts/deploy_production.py configure \
  --endpoint https://yousufricemill.com/v1 \
  --project-id YOUR_PRODUCTION_PROJECT_ID
```

The script asks for the Appwrite server key, OpenAI key, Jazz UAN, and Jazz
password with hidden input. It creates `.env.production` with owner-only
permissions and generates a shared internal token. This file is ignored by Git.
It refuses to overwrite an existing file. Existing production files can be
edited privately; keep dotenv quoting when editing passwords with special
characters. Model defaults are in `services/backend/app/config/settings.py`;
override them in `.env.production` when needed.

First inspect the deployment plan:

```bash
python3 scripts/deploy_production.py deploy --dry-run
```

Then deploy:

```bash
python3 scripts/deploy_production.py deploy
```

The helper reads `OPR_EXECUTOR_NETWORK` from the running Appwrite executor,
verifies the external network, builds Chromium/FFmpeg into the worker image,
bootstraps the project's schema and server-only recordings bucket, starts three
services, and checks readiness plus authorized/unauthorized API access from that
network. An ambiguous or unavailable network stops deployment. For a known
single runtime network, you can pass `--runtime-network NETWORK_NAME`.

The API keeps its host port bound to `127.0.0.1`; network access uses its private
Docker alias. Worker and scheduler have no published ports. All three restart
automatically. Discovery and processing release at **18:01 Asia/Karachi**, with
post-18:00 calls included in the following day's batch.

## 3. Connect GitHub in Appwrite Sites

Create the Site inside the same production project, connect this repository's
`main` branch, and use:

| Setting | Value |
|---|---|
| Repository root | `apps/web` |
| Framework / adapter | Next.js / SSR |
| Runtime | `node-22` |
| Install | `npm install -g pnpm@12.6.0 && pnpm install --frozen-lockfile` |
| Build | `pnpm build` |
| Output | `.next` |
| API scopes | `sessions.write` |

Use the HTTPS domain displayed in the Site's Domains tab. Your configured Sites
base domain determines the generated hostname; the scripts do not guess it.
You can add a custom hostname such as `calls.yousufricemill.com` through the
Console, following Appwrite's DNS/certificate instructions.

Configure these Site variables:

| Variable | Value | Secret? |
|---|---|---|
| `BACKEND_INTERNAL_URL` | `http://call-grader-api:8000` | No |
| `INTERNAL_API_TOKEN` | Same value from the VPS `.env.production` | **Yes** |
| `APP_ORIGIN` | Actual HTTPS Site origin, without a trailing slash | No |

Appwrite injects the Site's project ID and API endpoint. Do not copy Jazz,
OpenAI, or backend Appwrite keys into the Site. Login uses the Site's scoped
ephemeral key; account authorization uses the visitor's session.

### Optional automatic Site variable configuration

With the Appwrite CLI installed on the VPS, log in to the production instance:

```bash
appwrite login --endpoint https://yousufricemill.com/v1
python3 scripts/deploy_production.py configure-site \
  --site-id YOUR_SITE_ID \
  --site-origin https://YOUR_ACTUAL_SITE_HOSTNAME
```

This verifies the Site's framework, adapter, and login scope, and creates or
updates only the three variables above. It preserves other Site variables and
does not change the checked-in local Appwrite project link. Add `--dry-run` to
inspect the intended operation first. Redeploy the Site after configuring its
variables.

## 4. Verify and update

After the Site deployment becomes ready:

1. Signed-out visitors must land on sign-in.
2. A project account without `admin` must be denied.
3. An admin account must see reports and the System page, and play a recording.
4. Removing its `admin` label must deny further page and audio requests.
5. Sign-out must return to login. Check the next scheduled batch on System.

For later backend updates:

```bash
git pull --ff-only
python3 scripts/deploy_production.py deploy
```

Git-connected Sites can rebuild from subsequent pushes according to their
production branch settings. Preserve `.env.production` and Docker volumes when
updating. If you rotate the internal token, rerun `configure-site` and redeploy
the Site too.

## Appwrite Functions

Appwrite supports background Function executions up to the configured timeout
(normally 900 seconds); synchronous HTTP Function requests have a 30-second
limit. The existing worker and scheduler are continuous processes. Deploying
them as Functions requires bounded invocations, safe coordination between
concurrent executions, and verified Chromium/FFmpeg packaging. The upstream
standard Python runtime uses Alpine; that is a different environment from this
project's verified Debian-based worker. The production runtime has not been
inspected or tested here. A 15-minute setting alone does not verify compatibility.

The scripts in this guide deploy the existing Docker pipeline. They do not
claim to migrate it to Functions. A Functions migration should be tested in a
separate deployment before switching the live processing schedule.

References:

- [Appwrite execution modes and timeouts](https://appwrite.io/docs/products/functions/execute)
- [Upstream Python runtime images](https://github.com/open-runtimes/open-runtimes/blob/main/ci/runtimes.toml)
- [Executor runtime networking](https://github.com/open-runtimes/executor/blob/main/src/Executor/Runner/Docker.php)
- [Playwright container requirements](https://playwright.dev/python/docs/docker)
- [Self-hosted Sites domains](https://appwrite.io/docs/advanced/self-hosting/configuration/sites)
