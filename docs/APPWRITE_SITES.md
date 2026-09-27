# Appwrite authentication and Sites deployment

## Access policy

Only a signed-in Appwrite project account with the exact server-managed `admin`
label can access this app. User preferences, form fields, and browser-stored roles
are never accepted as authorization. The server checks Appwrite's current account
on every private data request and server action. Disabled accounts, expired or
revoked sessions, incomplete MFA, and Appwrite outages fail closed.

Sessions are stored in a host-only, HTTP-only cookie with `SameSite=Strict` and
`Secure` in production. They expire with Appwrite's session. Login and logout
require the same origin. Logout revokes the current Appwrite session. A denied
non-admin login revokes its newly created session and sets no session cookie.
There is no public sign-up or user-label editing endpoint.

The dashboard, reports, calls, agent/settings pages, server actions, and private
audio proxy are protected. Backend calls use a server-only internal token and
the verified account ID for audit attribution. The backend rejects requests when
that token is missing or incorrect, and fails closed if it is not configured.

## Hosting in one Appwrite project

- **Appwrite Functions:** private API, discovery, queued processing, retention.
- **Appwrite:** authentication, database, private recording storage.
- **Appwrite Sites:** Next.js frontend, SSR mode, framework `nextjs`, runtime `node-22`.

Use [Functions deployment](APPWRITE_FUNCTIONS.md) for the complete automated setup.

## Sites configuration

| Setting | Value |
|---|---|
| Repository root directory | `apps/web` |
| Framework | `nextjs` |
| Adapter | `ssr` |
| Build runtime | `node-22` |
| Install command | `npm install -g pnpm@12.6.0 && pnpm install --frozen-lockfile` |
| Build command | `pnpm build` |
| Output directory | `.next` |
| Site scopes | `sessions.write`, `execution.write`, `files.read` |

Appwrite Sites injects `APPWRITE_SITE_API_ENDPOINT` and
`APPWRITE_SITE_PROJECT_ID`. The login handler uses the ephemeral `x-appwrite-key`
SSR request header when running in Sites. The key uses the scopes above;
account authorization uses the visitor's session, never an API key.

Set these site variables:

- `APPWRITE_BACKEND_FUNCTION_ID`: `call-grader-api`.
- `INTERNAL_API_TOKEN`: **secret**; must match the API Function variable.
- `APPWRITE_RECORDINGS_BUCKET_ID`: `call_recordings` (the default).
- `APPWRITE_ENDPOINT` and `APPWRITE_PROJECT_ID`: optional server endpoint overrides; the helper sets them to the selected target.
- `APP_ORIGIN`: optional exact site origin if the proxy changes the request host.

The Site invokes the API Function privately through the Server SDK. Its protected
audio route reads the recording directly from Storage after checking admin access.

For local Docker or a host without Sites' ephemeral request key, configure
`APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, and the **server-only**
`APPWRITE_AUTH_API_KEY` with only `sessions.write`. A dedicated local key was
created during verification. It is excluded from every source package/image.

## GitHub deployment through the production Console

1. Use the GitHub repository `MuhammadWahajYousufzai/call-grader`, branch `main`.
2. In the production Appwrite project, open **Sites**, create a Site, and connect
   the GitHub repository. Choose `main` as the production branch.
3. Set the repository root directory to `apps/web`. Apply the Next.js SSR build
   settings and all three Site scopes in the table above.
4. Run the [Functions deployment helper](APPWRITE_FUNCTIONS.md) for the selected
   project. It deploys the backend Functions and configures
   `APPWRITE_BACKEND_FUNCTION_ID`, secret `INTERNAL_API_TOKEN`, and the server
   endpoint/project variables. Set `APP_ORIGIN` to the final HTTPS origin if
   your proxy changes the request host.
5. Deploy and wait for the build to reach `ready`. Verify the deployed URL:
   anonymous requests redirect to sign-in, non-admin accounts are denied, admin
   accounts can read reports, and removing the admin label denies subsequent
   dashboard/audio requests. Check playback and sign-out too.

The GitHub repository contains source and dependency lockfiles. Environment
files, recordings, local builds, dependencies, caches, and upload archives are
excluded by `.gitignore`. Set production secrets in Appwrite variables; do not
place them in GitHub source or public browser variables.

`appwrite.config.json` records the local development project and schema. Its
Site source path is `apps/web`. Connecting GitHub in the production Console does
not require pushing this local project configuration to production. The
`scripts/prepare_appwrite_site.py` source packager remains available for optional
manual uploads; GitHub deployment builds directly from the tracked frontend.

## Verification

The deployed local Appwrite Site has been checked for anonymous/non-admin denial,
admin Dashboard/System/report access, private playback and immediate admin-label
revocation. Repeat the browser checks using `deploy_appwrite.py verify --site-url`
as documented in [production setup](PRODUCTION_SETUP.md). Tests and verification
history are recorded in [VERIFICATION.md](VERIFICATION.md).

## References

- [Appwrite SSR authentication](https://appwrite.io/docs/products/auth/server-side-rendering)
- [Sites ephemeral keys and scopes](https://appwrite.io/docs/products/sites/develop)
- [Sites variables](https://appwrite.io/docs/products/sites/environment-variables)
- [Next.js Sites deployment](https://appwrite.io/docs/products/sites/quick-start/nextjs)
