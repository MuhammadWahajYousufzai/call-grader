"""Configure and deploy the Docker backend beside an existing self-hosted Appwrite.

Run on the VPS. Uses Appwrite's runtime network so Sites can reach the API
without adding a public API domain, a second reverse proxy, or changing Appwrite.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ["backend-api", "backend-worker", "backend-scheduler"]
PRIVATE_URL = "http://call-grader-api:8000"


class DeployError(Exception):
    pass


def run(command: list[str], env: dict[str, str], *, redact: tuple[str, ...] = (),
        safe_error: str | None = None) -> str:
    result = subprocess.run(command, env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        if safe_error:
            raise DeployError(safe_error)
        detail = result.stderr or result.stdout
        for value in redact:
            if value:
                detail = detail.replace(value, "[redacted]")
        raise DeployError(f"{command[0]} failed: {detail[-3000:]}")
    return result.stdout


def validate_target(endpoint: str, project: str) -> None:
    parsed = urlparse(endpoint)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path != "/v1"
            or parsed.hostname in ("localhost", "127.0.0.1", "::1")):
        raise DeployError("Use the production HTTPS Appwrite endpoint ending in /v1.")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,35}", project):
        raise DeployError("Enter the production Appwrite project ID from the Console.")


def write_env(path: Path, values: dict[str, str]) -> None:
    if any("\n" in value or "\r" in value for value in values.values()):
        raise DeployError("Environment values must fit on one line.")
    # Compose resolves $$ to a literal dollar in double-quoted dotenv values.
    content = "# Production backend configuration; keep this file private.\n"
    content += "\n".join(
        f"{key}={json.dumps(value, ensure_ascii=False).replace('$', '$$')}"
        for key, value in values.items()
    ) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DeployError(f"{path.name} already exists; edit it or choose another --env-file.") from exc
    with os.fdopen(fd, "w") as file:
        file.write(content)


def configure(args) -> None:
    if not sys.stdin.isatty():
        raise DeployError("Run configure in an interactive terminal so credential input stays hidden.")
    endpoint = (args.endpoint or input("Production Appwrite endpoint [https://yousufricemill.com/v1]: ")
                or "https://yousufricemill.com/v1").rstrip("/")
    project = args.project_id or input("Production Appwrite project ID: ").strip()
    validate_target(endpoint, project)
    values = {
        "APP_ENV": "production", "TZ": "Asia/Karachi", "APP_TIMEZONE": "Asia/Karachi",
        "APPWRITE_ENDPOINT": endpoint, "APPWRITE_PROJECT_ID": project,
        "APPWRITE_DATABASE_ID": "call_grader", "APPWRITE_RECORDINGS_BUCKET_ID": "call_recordings",
        "APPWRITE_API_KEY": getpass.getpass("Production Appwrite server API key: "),
        "OPENAI_API_KEY": getpass.getpass("OpenAI API key: "),
        "JAZZ_UAN": getpass.getpass("Jazz UAN: "),
        "JAZZ_PASSWORD": getpass.getpass("Jazz password: "),
        "INTERNAL_API_TOKEN": secrets.token_urlsafe(48),
        "NEXT_PUBLIC_APPWRITE_ENDPOINT": endpoint, "NEXT_PUBLIC_APPWRITE_PROJECT_ID": project,
        "BACKEND_INTERNAL_URL": PRIVATE_URL,
        "JAZZ_HEADLESS": "true", "JAZZ_SYNC_CRON": "1 18 * * *",
        "BUSINESS_DAY_START": "09:30", "BUSINESS_DAY_END": "18:00",
    }
    if not all(values[key] for key in ("APPWRITE_API_KEY", "OPENAI_API_KEY", "JAZZ_UAN", "JAZZ_PASSWORD")):
        raise DeployError("All four credentials are required; no file was written.")
    write_env(args.env_file, values)
    print(f"Created {args.env_file.name} with owner-only permissions and a generated internal token.")
    print("Next: python3 scripts/deploy_production.py deploy")


def runtime_network(env: dict[str, str], explicit: str | None) -> str:
    if explicit:
        name = explicit
    else:
        ids = run(["docker", "ps", "-q"], env).split()
        if not ids:
            raise DeployError("No running Appwrite executor found on this Docker host.")
        containers = json.loads(run(["docker", "inspect", *ids], env))
        networks = set()
        for container in containers:
            if "openruntimes/executor" not in container.get("Config", {}).get("Image", ""):
                continue
            variables = dict(item.split("=", 1) for item in container["Config"].get("Env", []) if "=" in item)
            if variables.get("OPR_EXECUTOR_NETWORK"):
                networks.add(variables["OPR_EXECUTOR_NETWORK"])
        if len(networks) != 1:
            raise DeployError("Cannot select one runtime network; pass --runtime-network from OPR_EXECUTOR_NETWORK.")
        name = networks.pop()
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", name):
        raise DeployError("Invalid runtime network name.")
    run(["docker", "network", "inspect", name], env)
    return name


def compose(env_file: Path, network: str | None = None) -> tuple[list[str], dict[str, str]]:
    env = dict(os.environ, CALL_GRADER_ENV_FILE=str(env_file))
    command = ["docker", "compose", "--project-name", "call-grader", "--env-file", str(env_file),
               "-f", str(ROOT / "docker-compose.prod.yml")]
    if network:
        env["APPWRITE_RUNTIME_NETWORK"] = network
        command += ["-f", str(ROOT / "docker-compose.appwrite-network.yml")]
    return command, env


def configuration(args) -> tuple[dict[str, str], list[str], dict[str, str]]:
    if not args.env_file.is_file():
        raise DeployError("Production environment file missing. Run the configure command first.")
    args.env_file.chmod(0o600)
    command, env = compose(args.env_file)
    data = json.loads(run(command + ["config", "--format", "json"], env,
                          safe_error="Docker Compose could not read the production configuration. Check the env file and Compose installation."))
    # `compose config` escapes literal dollars for reusable Compose output.
    values = {key: value.replace("$$", "$") if isinstance(value, str) else value
              for key, value in data["services"]["backend-api"]["environment"].items()}
    validate_target(values.get("APPWRITE_ENDPOINT", ""), values.get("APPWRITE_PROJECT_ID", ""))
    missing = [key for key in ("APPWRITE_API_KEY", "OPENAI_API_KEY", "JAZZ_UAN", "JAZZ_PASSWORD", "INTERNAL_API_TOKEN")
               if not values.get(key)]
    if missing:
        raise DeployError("Missing production variables: " + ", ".join(missing))
    if len(values["INTERNAL_API_TOKEN"]) < 32:
        raise DeployError("INTERNAL_API_TOKEN must contain at least 32 characters.")
    return values, command, env


def deploy(args) -> None:
    values, _, env = configuration(args)
    if args.dry_run:
        print(f"Target: {values['APPWRITE_ENDPOINT']} / project {values['APPWRITE_PROJECT_ID']}")
        print("Plan: discover runtime network; build API/worker; bootstrap project; start three backend services.")
        print("Then verify readiness and protected API access from the runtime network.")
        print(f"Sites BACKEND_INTERNAL_URL={PRIVATE_URL}")
        print("Dry run: no containers or Appwrite resources were changed.")
        return
    network = runtime_network(env, args.runtime_network)
    command, env = compose(args.env_file, network)
    hidden = tuple(str(values[k]) for k in ("APPWRITE_API_KEY", "OPENAI_API_KEY", "JAZZ_UAN", "JAZZ_PASSWORD", "INTERNAL_API_TOKEN"))
    # Reject an API alias owned by another deployment instead of sharing its DNS name.
    info = json.loads(run(["docker", "network", "inspect", network], env))[0]
    ids = list((info.get("Containers") or {}).keys())
    if ids:
        for container in json.loads(run(["docker", "inspect", *ids], env)):
            aliases = container.get("NetworkSettings", {}).get("Networks", {}).get(network, {}).get("Aliases") or []
            labels = container.get("Config", {}).get("Labels") or {}
            if "call-grader-api" in aliases and labels.get("com.docker.compose.project") != "call-grader":
                raise DeployError("call-grader-api alias is already owned by another deployment.")
    print(f"Deploying project {values['APPWRITE_PROJECT_ID']} on runtime network {network}.", flush=True)
    print("Building backend images (Chromium and FFmpeg included)...", flush=True)
    run(command + ["build", "backend-api", "backend-worker"], env, redact=hidden)
    if not args.skip_bootstrap:
        print("Preparing Appwrite schema and private recordings bucket...", flush=True)
        for attempt in range(3):
            output = run(command + ["run", "--rm", "--no-deps", "backend-api", "python", "/srv/scripts/bootstrap_appwrite.py"], env, redact=hidden)
            errors = [line for line in output.splitlines() if line.lstrip().startswith("!")]
            if not errors:
                break
            if attempt == 2:
                detail = "\n".join(errors)
                for value in hidden:
                    detail = detail.replace(value, "[redacted]")
                raise DeployError("Schema preparation reported errors; backend was not started.\n" + detail[-2000:])
            print("Retrying idempotent schema preparation after provisioning settles...", flush=True)
            time.sleep(5)
    print("Starting API, worker, and scheduler...", flush=True)
    run(command + ["up", "-d", "--no-build", *SERVICES], env, redact=hidden)
    ready_code = (
        "import json,urllib.request; "
        "r=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health/ready',timeout=10)); "
        "assert r.get('ok') and r.get('appwrite')"
    )
    for attempt in range(30):
        try:
            run(command + ["exec", "-T", "backend-api", "python", "-c", ready_code], env, redact=hidden)
            break
        except DeployError:
            if attempt == 29:
                raise DeployError("Backend is not ready. Inspect backend-api logs; deployment did not pass verification.") from None
            time.sleep(2)
    # This short-lived probe joins the same network as Appwrite runtime containers.
    image = json.loads(run(command + ["config", "--format", "json"], env))["services"]["backend-api"]["image"]
    probe = f"""import json, os, urllib.request, urllib.error
base = {PRIVATE_URL!r}
assert json.load(urllib.request.urlopen(base + '/health/ready', timeout=15))['ok']
try:
    urllib.request.urlopen(base + '/api/reports?limit=1', timeout=15)
except urllib.error.HTTPError as error:
    assert error.code == 401
else:
    raise RuntimeError('API allowed an unauthenticated request')
req = urllib.request.Request(base + '/api/reports?limit=1',
    headers={{'x-internal-token': os.environ['INTERNAL_API_TOKEN']}})
assert 'reports' in json.load(urllib.request.urlopen(req, timeout=15))
"""
    probe_env = dict(env, INTERNAL_API_TOKEN=values["INTERNAL_API_TOKEN"])
    run(["docker", "run", "--rm", "--network", network, "--env", "INTERNAL_API_TOKEN",
         "--entrypoint", "python", image, "-c", probe], probe_env, redact=hidden)
    print("Backend readiness and authenticated access from the runtime network passed.")
    print(f"Set Sites BACKEND_INTERNAL_URL={PRIVATE_URL}")
    print(f"Copy INTERNAL_API_TOKEN from {args.env_file.name} into a secret Site variable, then redeploy the Site.")
    print("Daily processing: 18:01 Asia/Karachi. Existing Appwrite services were not restarted.")


def configure_site(args) -> None:
    if not args.site_id or not args.site_origin:
        raise DeployError("configure-site requires --site-id and --site-origin from the production Console.")
    parsed = urlparse(args.site_origin)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise DeployError("--site-origin must be the public HTTPS origin of the Site.")
    origin = f"https://{parsed.netloc}"
    values, _, env = configuration(args)
    # These explicit overrides select production without changing the local CLI config.
    env.update(APPWRITE_ENDPOINT=values["APPWRITE_ENDPOINT"], APPWRITE_PROJECT_ID=values["APPWRITE_PROJECT_ID"])
    hidden = tuple(str(values[key]) for key in ("APPWRITE_API_KEY", "OPENAI_API_KEY", "JAZZ_UAN", "JAZZ_PASSWORD", "INTERNAL_API_TOKEN"))
    site = json.loads(run(["appwrite", "sites", "get", "--site-id", args.site_id, "--json"], env, redact=hidden))
    if site.get("framework") != "nextjs" or site.get("adapter") != "ssr":
        raise DeployError("Select Next.js with SSR in the production Site settings first.")
    if "sessions.write" not in site.get("scopes", []):
        raise DeployError("Enable the sessions.write scope in the Site settings first.")
    settings = {"BACKEND_INTERNAL_URL": PRIVATE_URL, "INTERNAL_API_TOKEN": values["INTERNAL_API_TOKEN"], "APP_ORIGIN": origin}
    if args.dry_run:
        print("Verified target Site. Would set BACKEND_INTERNAL_URL, secret INTERNAL_API_TOKEN, and APP_ORIGIN.")
        print("Dry run: no Site variables were changed.")
        return
    result = json.loads(run(["appwrite", "sites", "list-variables", "--site-id", args.site_id,
                             "--filter", "key=" + json.dumps(list(settings)), "--limit", "100", "--json"], env, redact=hidden))
    existing = {variable["key"]: variable["$id"] for variable in result.get("variables", [])}
    for key, value in settings.items():
        action = "update-variable" if key in existing else "create-variable"
        variable_id = existing.get(key, "call-grader-" + key.lower())
        command = ["appwrite", "sites", action, "--site-id", args.site_id,
                   "--variable-id", variable_id, "--key", key, "--value", value, "--json"]
        if key == "INTERNAL_API_TOKEN":
            command.append("--secret")
        run(command, env, redact=hidden)
        print(f"Configured Site variable {key}.")
    print("Redeploy the Site in the Console, then verify sign-in, System status, and audio playback.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("configure", "deploy", "configure-site"))
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.production")
    parser.add_argument("--endpoint")
    parser.add_argument("--project-id")
    parser.add_argument("--runtime-network")
    parser.add_argument("--site-id")
    parser.add_argument("--site-origin")
    parser.add_argument("--skip-bootstrap", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.env_file = args.env_file.resolve()
    try:
        if args.action == "configure":
            if args.dry_run:
                raise DeployError("--dry-run applies to deploy; configure writes a new private file.")
            configure(args)
        elif args.action == "deploy":
            deploy(args)
        else:
            configure_site(args)
    except (DeployError, FileNotFoundError) as exc:
        print(f"Deployment stopped: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
