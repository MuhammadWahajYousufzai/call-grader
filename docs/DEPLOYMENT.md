# Deployment and operations

Deploy six private Appwrite Functions and the Next.js frontend on Appwrite Sites
in one project. Follow [production setup](PRODUCTION_SETUP.md) and
[Functions settings](APPWRITE_FUNCTIONS.md). Existing Appwrite remains in place.

Run `python3 scripts/deploy_appwrite.py verify` after every deployment. Functions
use native Appwrite schedules and durable jobs; no separate containers are needed.

See [operations](OPERATIONS.md) for retries, retention and backups.
