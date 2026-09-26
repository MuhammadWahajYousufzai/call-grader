# Local setup

See README steps 1–5. Checklist:

1. `docker ps` shows `appwrite` healthy on `:80` (repo at `/Desktop/appwrite/appwrite`).
2. `cp .env.example .env` and fill Appwrite project/key, OpenAI key, Jazz creds, `INTERNAL_API_TOKEN`.
3. `cd services/backend && uv sync && uv run python ../../scripts/bootstrap_appwrite.py`.
4. `uv run pytest -q` green.
5. Start `make api`, `make worker`, and `make scheduler` in separate terminals,
   then `pnpm --dir apps/web dev`. The scheduler logs into Jazz with `.env`
   credentials and starts today's batch at 18:01 Karachi. A first morning run
   waits until then; a restart catches up any missed closed batches. Later runs
   resume from the persisted call cursor and include the prior day's post-18:00
   calls. The worker resumes incomplete
   recordings and AI jobs automatically.
6. Open `http://localhost:3000/dashboard`.
