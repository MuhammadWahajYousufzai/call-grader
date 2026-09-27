"""Native runtime preparation and per-execution Appwrite authentication."""

import os
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/backend"))


def prepare_native():
    native = ROOT / "native"
    if not native.exists():
        return
    os.environ["PATH"] = f"{native}/usr/bin:{native}/bin:" + os.environ.get("PATH", "")
    os.environ["LD_LIBRARY_PATH"] = f"{native}/usr/lib:{native}/usr/lib/pulseaudio:{native}/lib:" + os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["PLAYWRIGHT_NODEJS_PATH"] = str(native / "usr/bin/node")
    browser = next((p for p in (native / "usr/lib/chromium/chromium", native / "usr/lib/chromium/chrome") if p.exists()), None)
    if browser is None:
        raise RuntimeError("Bundled Chromium executable missing")
    os.environ["JAZZ_CHROMIUM_EXECUTABLE"] = str(browser)
    fonts = Path("/tmp/call-grader-fonts.conf")
    fonts.write_text(f'<fontconfig><dir>{native}/usr/share/fonts</dir><cachedir>/tmp/call-grader-font-cache</cachedir></fontconfig>')
    os.environ["FONTCONFIG_FILE"] = str(fonts)


@contextmanager
def invocation(context):
    prepare_native()
    from app.appwrite.client import execution_credentials

    headers = {key.lower(): value for key, value in context.req.headers.items()}
    key = headers.get("x-appwrite-key", "")
    if not key:
        raise RuntimeError("Appwrite execution key missing")
    endpoint = os.environ.get("APPWRITE_ENDPOINT") or os.environ.get("APPWRITE_FUNCTION_API_ENDPOINT", "")
    project = os.environ.get("APPWRITE_PROJECT_ID") or os.environ.get("APPWRITE_FUNCTION_PROJECT_ID", "")
    if not endpoint or not project:
        raise RuntimeError("Appwrite Function project configuration missing")
    os.environ["APPWRITE_ENDPOINT"] = endpoint
    os.environ["APPWRITE_PROJECT_ID"] = project
    with execution_credentials(endpoint, project, key):
        yield


def runtime_check():
    import subprocess
    import tempfile

    from app.functions.pipeline import run_worker
    from app.jazz.client import JazzClient
    from app.jazz.downloader import verify_audio

    with JazzClient() as browser:
        page = browser._page()
        page.set_content('<table id="runtime-test"><tr><td>ready</td></tr></table>')
        assert page.locator("#runtime-test td").inner_text() == "ready"
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "check.wav"
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(path)],
                       check=True, capture_output=True, timeout=30)
        info = verify_audio(path)
    assert callable(run_worker)
    return {"pipeline_import": True, "chromium": True, "ffmpeg": True,
            "ffprobe": True, "audio_seconds": info["duration"]}


def request_body(context):
    import json

    # Cron executions have no body. Appwrite's body_json property raises for
    # an empty string, so decode only after providing the default object.
    body = json.loads(context.req.body_text or "{}")
    if not isinstance(body, dict):
        raise ValueError("JSON object required")
    return body


async def run_child(context, role: str):
    """Run synchronous browser/AI code outside Appwrite's asyncio server.

    Kill the whole process group before the platform timeout. This also closes
    Chromium, and leaves durable leases/checkpoints for the next execution.
    """
    import tempfile

    # Runtime containers are reused. Remove downloaded/chunked audio after
    # success, failure, or timeout instead of filling their temporary disk.
    with tempfile.TemporaryDirectory(prefix="call-grader-audio-") as directory:
        return await _run_child(context, role, directory)


async def _run_child(context, role: str, audio_directory: str):
    import asyncio
    import json
    import signal

    try:
        body = request_body(context)
    except ValueError:
        return context.res.json({"error": "JSON object required"}, 400)
    request = {"role": role, "body": body, "headers": dict(context.req.headers)}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "infra.appwrite.runner", cwd=str(ROOT),
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, start_new_session=True,
        env={**os.environ, "LOCAL_AUDIO_DIR": audio_directory},
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(json.dumps(request).encode()), timeout=840)
    except (TimeoutError, asyncio.CancelledError):
        if process.returncode is None:
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        context.error("Execution budget exhausted; durable work will resume automatically.")
        return context.res.json({"error": "Execution budget exhausted"}, 503)
    line = next((line for line in reversed(stdout.decode().splitlines())
                 if line.startswith("FUNCTION_RESULT=")), None)
    # Gunicorn's SIGCHLD handler can reap the subprocess before asyncio's
    # watcher, which reports 255. Accept its explicit completed-result marker.
    if process.returncode and not (process.returncode == 255 and line):
        message = stderr.decode(errors="replace")[-3000:]
        private = [value for name, value in os.environ.items()
                   if any(word in name for word in ("KEY", "PASSWORD", "TOKEN", "UAN"))]
        private.append(request["headers"].get("x-appwrite-key", ""))
        for value in private:
            if value:
                message = message.replace(value, "[redacted]")
        context.error(f"Child exited with status {process.returncode}: {message}")
        return context.res.json({"error": "Execution failed; inspect Function logs"}, 503)
    if not line:
        return context.res.json({"error": "Function returned no result"}, 503)
    result = json.loads(line.split("=", 1)[1])
    context.log(json.dumps(result))
    return context.res.json(result)
