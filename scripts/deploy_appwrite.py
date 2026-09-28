"""Deploy the backend Functions and Next.js Site into one Appwrite project.

Uses the existing Appwrite CLI login, preserves unrelated resources/variables,
packages only source files, and enables schedules after bootstrap/runtime checks.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_FILE = ROOT / ".env.appwrite-production.json"


class DeployError(Exception):
    pass


def validate_target(endpoint: str, project: str) -> None:
    parsed = urlparse(endpoint)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path != "/v1"
            or parsed.hostname in ("localhost", "127.0.0.1", "::1")
            or parsed.hostname.endswith(".localhost")):
        raise DeployError("Use the production HTTPS Appwrite endpoint ending in /v1.")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,35}", project):
        raise DeployError("Enter the production Appwrite project ID from the Console.")


def configuration(args):
    if args.config.stat().st_mode & 0o077:
        raise DeployError("Private configuration must have owner-only permissions: chmod 600 " + args.config.name)
    try:
        values = json.loads(args.config.read_text())
        required = ("APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "GEMINI_API_KEY",
                    "JAZZ_UAN", "JAZZ_PASSWORD", "INTERNAL_API_TOKEN",
                    "GEMINI_TRANSCRIBE_MODEL", "GEMINI_GRADING_MODEL", "GEMINI_ROMANIZER_MODEL")
        if any(not isinstance(values.get(key), str) or not values[key].strip() for key in required):
            raise ValueError
    except (ValueError, TypeError):
        raise DeployError("Private configuration is invalid or missing required credentials.") from None
    endpoint, project = values["APPWRITE_ENDPOINT"], values["APPWRITE_PROJECT_ID"]
    if args.local:
        local_project = json.loads((ROOT / "appwrite.config.json").read_text())["projectId"]
        if endpoint != "http://localhost/v1" or project != local_project:
            raise DeployError("--local must target the linked localhost development project.")
    else:
        validate_target(endpoint, project)
    if args.local:
        # Re-read the selected provider credentials when a key is replaced in .env.
        from dotenv import dotenv_values
        source = dotenv_values(ROOT / ".env")
        for key in ("GEMINI_API_KEY", "GEMINI_TRANSCRIBE_MODEL", "GEMINI_GRADING_MODEL",
                    "GEMINI_ROMANIZER_MODEL", "GEMINI_REQUESTS_PER_MINUTE",
                    "GEMINI_TIMEOUT_SECONDS", "GEMINI_MAX_OUTPUT_TOKENS"):
            if source.get(key):
                values[key] = source[key]
    if getattr(args, "flash_model", None):
        values["GEMINI_ROMANIZER_MODEL"] = args.flash_model
        values["GEMINI_GRADING_MODEL"] = args.flash_model
    return values, {**os.environ, "APPWRITE_ENDPOINT": endpoint, "APPWRITE_PROJECT_ID": project}


def command(args, directory, env, *, json_output=False, private_values=()):
    process = subprocess.run(["appwrite", *args, *( ["--json"] if json_output else [])],
                             cwd=directory, env=env, capture_output=True, text=True, check=False)
    output = process.stdout + process.stderr
    if process.returncode or "✗ Error:" in output:
        for value in private_values:
            if value:
                output = output.replace(value, "[redacted]")
        raise DeployError(output[-3000:])
    if json_output:
        return json.loads(process.stdout)
    return output


def configure(args):
    if args.local:
        from dotenv import dotenv_values

        source = dotenv_values(ROOT / ".env")
        config = {key: source.get(key, "") for key in (
            "APPWRITE_ENDPOINT", "APPWRITE_PROJECT_ID", "GEMINI_API_KEY", "JAZZ_UAN",
            "JAZZ_PASSWORD", "INTERNAL_API_TOKEN")}
        for key in ("GEMINI_TRANSCRIBE_MODEL", "GEMINI_GRADING_MODEL", "GEMINI_ROMANIZER_MODEL"):
            config[key] = source.get(key, "")
        config["APPWRITE_ENDPOINT"] = "http://localhost/v1"
        if not all(config.values()):
            raise DeployError("Local .env is missing required credentials.")
        fd = os.open(args.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as file:
            json.dump(config, file)
        print("Prepared local Appwrite configuration from the existing private .env.")
        return
    endpoint = args.endpoint.rstrip("/")
    project = args.project_id or input("Production project ID from Appwrite Console: ").strip()
    validate_target(endpoint, project)
    config = {"APPWRITE_ENDPOINT": endpoint, "APPWRITE_PROJECT_ID": project,
              "GEMINI_API_KEY": getpass.getpass("Gemini API key: "),
              "JAZZ_UAN": getpass.getpass("Jazz UAN: "),
              "JAZZ_PASSWORD": getpass.getpass("Jazz password: "),
              "INTERNAL_API_TOKEN": secrets.token_urlsafe(48),
              "GEMINI_TRANSCRIBE_MODEL": "gemini-3.5-transcribe",
              "GEMINI_GRADING_MODEL": "gemini-3.8-flash",
              "GEMINI_ROMANIZER_MODEL": "gemini-3.8-flash"}
    if not all(config.values()):
        raise DeployError("All credentials are required.")
    fd = os.open(args.config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(config, file)
    print(f"Saved private configuration to {args.config.name}. No permanent Appwrite server key is needed.")


def variables(resource, resource_id, values, directory, env, private_values):
    flag = "--function-id" if resource == "functions" else "--site-id"
    existing = command([resource, "list-variables", flag, resource_id, "--limit", "100"],
                       directory, env, json_output=True)["variables"]
    by_key = {item["key"]: item["$id"] for item in existing}
    for key, value in values.items():
        args = [resource, "update-variable" if key in by_key else "create-variable",
                flag, resource_id, "--key", key, "--value", value,
                "--variable-id", by_key.get(key, sha256(f"{resource_id}:{key}".encode()).hexdigest()[:32]), "--secret"]
        command(args, directory, env, private_values=private_values)


def cleanup_local_build(project, deployment_id):
    """Remove only this completed deployment's disposable build containers."""
    prefix = f"job-{project}-{deployment_id}-build-"
    result = subprocess.run(["docker", "ps", "-a", "--filter", f"name={prefix}",
                             "--filter", "status=exited", "--format", "{{.Names}}"],
                            capture_output=True, text=True, check=True)
    names = [name for name in result.stdout.splitlines()
             if name in (prefix + "worker", prefix + "sidecar")]
    if names:
        subprocess.run(["docker", "container", "rm", *names],
                       capture_output=True, text=True, check=True)


def function_metadata(function):
    """CLI update sends empty arrays/defaults, so supply the complete settings."""
    args = ["functions", "update", "--function-id", function["$id"],
            "--name", function["name"], "--runtime", function["runtime"],
            "--entrypoint", function["entrypoint"], "--commands", function["commands"],
            "--schedule", function["schedule"], "--timeout", str(function["timeout"]),
            "--deployment-retention", str(function["deploymentRetention"]),
            "--build-specification", function["buildSpecification"],
            "--runtime-specification", function["runtimeSpecification"],
            "--enabled" if function.get("enabled", True) else "--enabled=false", "--logging"]
    for scope in function["scopes"]:
        args.extend(["--scopes", scope])
    # This app intentionally has no client execution permissions or events.
    if function["execute"] or function["events"]:
        raise DeployError("Function client execution permissions/events must remain empty.")
    return args


def site_metadata(site):
    args = ["sites", "update", "--site-id", site["$id"], "--name", site["name"],
            "--framework", site["framework"], "--adapter", site["adapter"],
            "--build-runtime", site["buildRuntime"], "--install-command", site["installCommand"],
            "--build-command", site["buildCommand"], "--output-directory", site["outputDirectory"],
            "--fallback-file", site["fallbackFile"], "--timeout", str(site["timeout"]),
            "--deployment-retention", str(site["deploymentRetention"]),
            "--build-specification", site["buildSpecification"],
            "--runtime-specification", site["runtimeSpecification"], "--enabled", "--logging"]
    for scope in site["scopes"]:
        args.extend(["--scopes", scope])
    return args


def execute(function_id, body, directory, env, private_values, *, readiness=False):
    request = ["functions", "create-execution", "--function-id", function_id,
               "--async", "--body", json.dumps(body)]
    if readiness:
        request.extend(["--path", "/health/ready", "--method", "GET"])
    execution = command(request, directory, env, json_output=True)
    startup_retries = 0
    deadline = time.monotonic() + 960
    while time.monotonic() < deadline:
        result = command(["functions", "get-execution", "--function-id", function_id,
                          "--execution-id", execution["$id"]], directory, env, json_output=True)
        if result["status"] == "completed":
            if not 200 <= result.get("responseStatusCode", 0) < 300:
                raise DeployError(f"{function_id} returned an unsuccessful response.")
            response_body = result.get("responseBody")
            if response_body:
                return json.loads(response_body)
            # Appwrite omits responseBody for asynchronous executions.
            # Read the explicit result from Function logs instead.
            logs = result.get("logs", "")
            marker = "FUNCTION_RESULT_JSON="
            if marker in logs:
                return json.JSONDecoder().raw_decode(logs.split(marker, 1)[1])[0]
            for line in logs.splitlines():
                if line.startswith("{"):
                    return json.JSONDecoder().raw_decode(line)[0]
            if function_id == "call-grader-bootstrap" and "Bootstrap complete" in logs:
                return {"status": "SUCCESS"}
            raise DeployError(f"{function_id} completed but its result is unavailable; schedules remain paused.")
        if result["status"] == "failed":
            detail = result.get("errors", "")
            if "Timed out waiting for runtime" in detail and startup_retries < 2:
                startup_retries += 1
                execution = command(request, directory, env, json_output=True)
                continue
            for value in private_values:
                detail = detail.replace(value, "[redacted]") if value else detail
            raise DeployError(f"{function_id} execution failed: {detail[-2000:]}")
        time.sleep(5)
    raise DeployError(f"{function_id} execution did not finish; inspect its execution in Console.")


def deploy(args):
    values, env = configuration(args)
    endpoint, project = values["APPWRITE_ENDPOINT"], values["APPWRITE_PROJECT_ID"]
    private_values = tuple(values.values())
    template = json.loads((ROOT / "appwrite.config.json").read_text())
    with tempfile.TemporaryDirectory(prefix="call-grader-deploy-") as temporary:
        directory = Path(temporary)
        source = directory / "source"
        subprocess.run(["python3", str(ROOT / "scripts/prepare_appwrite_functions.py"),
                        "--output", str(source)], check=True)
        site_source = directory / "site"
        shutil.copytree(ROOT / "apps/web", site_source, ignore=shutil.ignore_patterns(
            ".env*", "node_modules", ".next", "*.tsbuildinfo", ".git", "*.log"))
        if list(site_source.rglob(".env*")):
            raise DeployError("Site source contains an environment file.")
        functions = [dict(item, path="source", schedule="", enabled=not bool(item["schedule"])) for item in template["functions"]]
        config = {"projectId": project, "endpoint": endpoint, "functions": functions,
                  "sites": [dict(template["sites"][0], path="site")]}
        (directory / "appwrite.config.json").write_text(json.dumps(config, indent=2))
        runtimes = command(["functions", "list-runtimes"], directory, env, json_output=True)["runtimes"]
        if not any(item["$id"] == "python-3.12" for item in runtimes):
            raise DeployError("Enable python-3.12 in the server's _APP_FUNCTIONS_RUNTIMES and restart the Appwrite API container. No Appwrite upgrade is required.")
        common = {"APP_ENV": "production", "PIPELINE_ENABLED": "false",
                  "APPWRITE_PROJECT_ID": project, "WORKER_LEASE_SECONDS": "1200",
                  "GEMINI_TIMEOUT_SECONDS": values.get("GEMINI_TIMEOUT_SECONDS", "120"),
                  "GEMINI_REQUESTS_PER_MINUTE": values.get("GEMINI_REQUESTS_PER_MINUTE", "2"),
                  "GEMINI_MAX_OUTPUT_TOKENS": values.get("GEMINI_MAX_OUTPUT_TOKENS", "16384"),
                  "GEMINI_DURABLE_RATE_LIMIT": "true",
                  "APPWRITE_SYNC_FUNCTION_ID": "call-grader-sync",
                  "APPWRITE_WORKER_FUNCTION_ID": "call-grader-worker"}
        common["APPWRITE_ENDPOINT"] = "http://host.docker.internal/v1" if args.local else endpoint
        # Clear schedules before code changes; jobs and checkpoints are preserved.
        for function in functions:
            function_id = function["$id"]
            print(f"Configuring {function_id} (schedules paused)…", flush=True)
            command(["push", "function", "--function-id", function_id, "--no-code", "--force"], directory, env, private_values=private_values)
            command(function_metadata(function), directory, env, private_values=private_values)
            role = function_id.removeprefix("call-grader-")
            role_values = dict(common)
            if role in ("sync", "worker"):
                role_values.update({key: values[key] for key in ("JAZZ_UAN", "JAZZ_PASSWORD")})
            if role == "worker":
                role_values.update({key: values[key] for key in (
                    "GEMINI_API_KEY", "GEMINI_TRANSCRIBE_MODEL", "GEMINI_GRADING_MODEL", "GEMINI_ROMANIZER_MODEL")})
            if role == "api":
                role_values["INTERNAL_API_TOKEN"] = values["INTERNAL_API_TOKEN"]
            variables("functions", function_id, role_values, directory, env, private_values)
        build_order = sorted(functions, key=lambda item: args.function_id.index(item["$id"])
                             if args.function_id and item["$id"] in args.function_id else len(functions))
        for function in build_order:
            if args.skip_function_builds or (args.function_id and function["$id"] not in args.function_id):
                current = command(["functions", "get", "--function-id", function["$id"]],
                                  directory, env, json_output=True)
                if not current.get("deploymentId"):
                    raise DeployError("Cannot resume: a Function has no active deployment.")
                continue
            print(f"Building {function['$id']}…", flush=True)
            command(["push", "function", "--function-id", function["$id"], "--activate", "--force", "--no-logs"], directory, env, private_values=private_values)
            if args.local:
                current = command(["functions", "get", "--function-id", function["$id"]],
                                  directory, env, json_output=True)
                cleanup_local_build(project, current["deploymentId"])
        # New source checks PIPELINE_ENABLED before business work. Enable only
        # after every build is ready, so legacy queued executions cannot run.
        for function in functions:
            command(function_metadata({**function, "enabled": True}), directory, env, private_values=private_values)
        print("Provisioning private database and recording bucket…", flush=True)
        execute("call-grader-bootstrap", {}, directory, env, private_values)
        for function_id in ("call-grader-worker", "call-grader-sync", "call-grader-catchup"):
            print(f"Checking pipeline imports and native runtime in {function_id}…", flush=True)
            check = execute(function_id, {"action": "runtime-check"}, directory, env, private_values)
            if not all(check.get(key) for key in ("pipeline_import", "chromium", "ffmpeg", "ffprobe")):
                raise DeployError("Native runtime check did not pass; schedules remain paused.")
        print("Checking API readiness before deploying the Site…", flush=True)
        ready = execute("call-grader-api", {}, directory, env, private_values, readiness=True)
        if ready.get("ok") is not True or ready.get("appwrite") is not True:
            raise DeployError("API cannot read Appwrite; schedules remain paused.")
        site_id = config["sites"][0]["$id"]
        command(["push", "site", "--site-id", site_id, "--no-code", "--force"], directory, env, private_values=private_values)
        variables("sites", site_id, {"APPWRITE_BACKEND_FUNCTION_ID": "call-grader-api",
                  "APPWRITE_ENDPOINT": common["APPWRITE_ENDPOINT"], "APPWRITE_PROJECT_ID": project,
                  "INTERNAL_API_TOKEN": values["INTERNAL_API_TOKEN"],
                  "APPWRITE_RECORDINGS_BUCKET_ID": "call_recordings"}, directory, env, private_values)
        print("Building the Next.js Site…", flush=True)
        command(["push", "site", "--site-id", site_id, "--activate", "--force", "--no-logs"], directory, env, private_values=private_values)
        # CLI push currently omits Site scopes; restore the full server settings
        # after the code push before admitting authenticated traffic.
        command(site_metadata(config["sites"][0]), directory, env, private_values=private_values)
        from verify_appwrite import verify_resources
        verify_resources(directory, env, private_values, paused=True, provisioning=True)
        for function in template["functions"]:
            if function["schedule"]:
                if not args.paused:
                    variables("functions", function["$id"], {"PIPELINE_ENABLED": "true"}, directory, env, private_values)
                target = {**function, "schedule": "", "enabled": False} if args.paused else function
                command(function_metadata(target), directory, env, private_values=private_values)
        if not args.paused:
            for function_id in ("call-grader-sync", "call-grader-worker"):
                command(["functions", "create-execution", "--function-id", function_id,
                         "--async", "--body", "{}"], directory, env, private_values=private_values)
        # Bootstrap stays private and has no cron. Its broad scopes are removed
        # after provisioning; the next deployment restores them for migration.
        bootstrap = next(f for f in functions if f["$id"] == "call-grader-bootstrap")
        command(function_metadata({**bootstrap, "scopes": ["databases.read"]}),
                directory, env, private_values=private_values)
    if args.paused:
        print("Deployed Functions + Site with all scheduled workloads disabled; no discovery or AI jobs started.")
        return
    print("Deployed Functions + Site. Discovery: 18:01 Karachi; catch-up: hourly; worker: every minute; retention: 02:30 Karachi.")
    print("In Console, connect the Site to GitHub (apps/web), set its domain, and assign the admin label to your account.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["configure", "deploy", "verify"])
    parser.add_argument("--config", type=Path)
    parser.add_argument("--flash-model", help="Override grading/Roman Urdu model for this deployment without changing private configuration")
    parser.add_argument("--paused", action="store_true", help="Keep scheduled workloads disabled and do not start initial jobs")
    parser.add_argument("--local", action="store_true", help="Target only the linked localhost development project")
    parser.add_argument("--function-id", action="append", help="Build only selected Functions; all other Functions must have active deployments")
    parser.add_argument("--skip-function-builds", action="store_true", help="Resume local verification after Function builds are already active")
    parser.add_argument("--endpoint", default="https://yousufricemill.com/v1")
    parser.add_argument("--project-id")
    parser.add_argument("--fresh-schema", action="store_true", help="Also test disposable fresh schema in the local project")
    parser.add_argument("--site-url", help="Also verify browser access using a temporary account (requires Playwright)")
    args = parser.parse_args()
    args.config = args.config or (ROOT / ".env.appwrite-local.json" if args.local else PRIVATE_FILE)
    if args.skip_function_builds and not args.local:
        raise SystemExit("--skip-function-builds is only available for local deployment recovery.")
    try:
        if args.action == "configure":
            configure(args)
        elif args.action == "verify":
            from verify_appwrite import verify
            verify(args)
        else:
            deploy(args)
            from verify_appwrite import verify
            verify(args)
    except (DeployError, FileNotFoundError, FileExistsError, KeyError, ValueError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    # Verification helpers import this module; share its exception type when the
    # entrypoint is executed as a script rather than imported as a module.
    sys.modules["deploy_appwrite"] = sys.modules[__name__]
    main()
