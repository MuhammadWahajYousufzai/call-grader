"""Install Playwright's pure Python driver with Alpine's native Node/Chromium."""

import platform
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
lock = tomllib.loads((root / "services/backend/uv.lock").read_text())
version = next(package["version"] for package in lock["package"] if package["name"] == "playwright")
arch = platform.machine()
if arch not in ("x86_64", "aarch64"):
    raise SystemExit(f"Unsupported runtime architecture: {arch}")
with tempfile.TemporaryDirectory() as temporary:
    command = [sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
               "--platform", f"manylinux_2_17_{arch}", "--platform", f"manylinux2014_{arch}",
               "--dest", temporary, f"playwright=={version}"]
    if arch == "x86_64":
        command[4:4] = ["--platform", "manylinux1_x86_64"]
    subprocess.run(command, check=True)
    wheel = next(Path(temporary).glob("*.whl"))
    with zipfile.ZipFile(wheel) as package:
        package.extractall(sysconfig.get_path("purelib"))
print("Installed pinned Playwright driver; native Node/Chromium are bundled separately.")
