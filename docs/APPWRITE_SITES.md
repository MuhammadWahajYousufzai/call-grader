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

## Hosting split

- Existing production Docker: FastAPI API, worker, and scheduler.
- Existing production Appwrite: account authentication, database, and recordings.
- **Appwrite Sites: Next.js frontend, SSR mode, framework `nextjs`, runtime `node-22`.**

The production Compose web container has the optional `local-preview` profile.
It is not part of the default production deployment when Sites hosts the frontend.

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
| Site scopes | `sessions.write` only |

Appwrite Sites injects `APPWRITE_SITE_API_ENDPOINT` and
`APPWRITE_SITE_PROJECT_ID`. The login handler uses the ephemeral `x-appwrite-key`
SSR request header when running in Sites. That key only needs `sessions.write`;
account authorization uses the visitor's session, never an API key.

Set these site variables:

- `BACKEND_INTERNAL_URL`: the production HTTPS API URL reachable from Sites.
- `INTERNAL_API_TOKEN`: **secret**; must match the deployed FastAPI environment.
- `APP_ORIGIN`: exact site origin, if the hosting proxy changes the request URL's origin.

For local Docker or a host without Sites' ephemeral request key, configure
`APPWRITE_ENDPOINT`, `APPWRITE_PROJECT_ID`, and the **server-only**
`APPWRITE_AUTH_API_KEY` with only `sessions.write`. A dedicated local key was
created during verification. It is excluded from every source package/image.

## GitHub deployment through the production Console

1. Create the GitHub repository and push the local `main` branch.
2. In the production Appwrite project, open **Sites**, create a Site, and connect
   the GitHub repository. Choose `main` as the production branch.
3. Set the repository root directory to `apps/web`. Apply the Next.js SSR build
   settings in the table above. Set the Site's API scopes to `sessions.write`.
4. Configure `BACKEND_INTERNAL_URL`, secret `INTERNAL_API_TOKEN`, and
   `APP_ORIGIN` using the production values described above. The backend must
   already be running and reachable from the Site runtime.
5. Deploy and wait for the build to reach `ready`. Verify the deployed URL:
   anonymous requests redirect to sign-in, non-admin accounts are denied, admin
   accounts can read reports, and removing the admin label denies subsequent
   dashboard/audio requests. Check playback and sign-out too.

The GitHub repository contains source and dependency lockfiles. Environment
files, recordings, local builds, dependencies, caches, and upload archives are
excluded by `.gitignore`. Set production secrets in Appwrite and the existing
Docker environment; do not place them in GitHub source or public browser variables.

`appwrite.config.json` records the local development project and schema. Its
Site source path is `apps/web`. Connecting GitHub in the production Console does
not require pushing this local project configuration to production. The
`scripts/prepare_appwrite_site.py` source packager remains available for optional
manual uploads; GitHub deployment builds directly from the tracked frontend.

## Verified locally on September 26

- Anonymous dashboard/report/call requests: redirect to login.
- Anonymous audio: HTTP 401.
- Non-admin login, including a forged `labels: ["admin"]` body: HTTP 403; no cookie.
- Admin login: HTTP 200; real September 25 report visible.
- Admin label removed: dashboard redirects to denied login; audio returns HTTP 403.
- Frontend tests: 15 pass. Backend tests: 32 pass; Ruff passes.
- Next.js production build and TypeScript pass.

The linked local development project is authenticated. The production Docker
image passed live admin login, non-admin rejection, secure/HTTP-only cookie,
protected-page/audio, and direct backend-token checks against local Appwrite.
Temporary verification accounts were deleted afterwards. Production Sites
deployment will be performed through the Console after the repository is on GitHub.

## References

- [Appwrite SSR authentication](https://appwrite.io/docs/products/auth/server-side-rendering)
- [Sites ephemeral keys and scopes](https://appwrite.io/docs/products/sites/develop)
- [Sites variables](https://appwrite.io/docs/products/sites/environment-variables)
- [Next.js Sites deployment](https://appwrite.io/docs/products/sites/quick-start/nextjs)
