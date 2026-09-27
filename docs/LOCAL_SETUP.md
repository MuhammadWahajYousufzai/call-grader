# Local setup

Run the same Functions + Sites architecture as production on the existing local
Appwrite at `http://localhost/v1`. Start Docker Desktop because it hosts Appwrite.
The repository does not deploy separate application containers.

```sh
uv run --project services/backend python scripts/deploy_appwrite.py configure --local
make deploy-local
make verify-local
```

Skip `configure` if the private `.env.appwrite-local.json` already exists. The
helper imports existing `.env` credentials, checks the linked local project,
packages source without secrets, builds Functions/Site, provisions schema, verifies
runtime tools and enables schedules. Allow at least 8 GB of free build disk.

Open the generated Site address under `sites.localhost`. Give the project account
the exact `admin` label. Local runtime calls reach Appwrite using
`http://host.docker.internal/v1`.

For browser access verification:

```sh
uv run --project services/backend python scripts/deploy_appwrite.py verify --local --fresh-schema --site-url http://YOUR_SITE.sites.localhost
```

The browser check creates and removes a temporary account. `--fresh-schema` also
creates disposable database/bucket resources, checks first-install provisioning
and repeat-safe seeds, then deletes those resources. Existing users, calls and
recordings are preserved. See [production setup](PRODUCTION_SETUP.md) for exact checks.

## Bounded Gemini testing

Keep application schedules disabled while testing the free key. See [Gemini](GEMINI.md).
For a fresh local deployment that performs runtime checks without starting jobs:

```sh
uv run --project services/backend python scripts/deploy_appwrite.py deploy --local --paused
uv run --project services/backend python scripts/deploy_appwrite.py verify --local --paused
```

`--paused` disables discovery, catch-up, worker and maintenance after the deployment
checks. It leaves the API and Site available. Deployment builds still need disk
space; the smoke helper runs directly on the host and does not require a rebuild.
