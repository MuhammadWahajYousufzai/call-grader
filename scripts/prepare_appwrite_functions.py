"""Produce a secret-free Python source directory for Appwrite Function builds."""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    if target.exists():
        raise SystemExit("Choose a fresh output directory.")
    target.mkdir(parents=True)
    ignore = shutil.ignore_patterns(".env*", "__pycache__", "*.pyc", "node_modules", ".next", ".venv")
    for name in ("services/backend/app", "infra/appwrite"):
        shutil.copytree(ROOT / name, target / name, ignore=ignore)
    for name in ("services/backend/pyproject.toml", "services/backend/uv.lock", "scripts/bootstrap_appwrite.py"):
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)
    assert not list(target.rglob(".env*"))
    print(f"Prepared Function source: {target}")


if __name__ == "__main__":
    main()
