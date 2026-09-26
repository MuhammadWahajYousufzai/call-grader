"""Package only Next.js source for Appwrite Sites; excludes all environment files."""

from __future__ import annotations

import argparse
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("/tmp/call-grader-sites"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / "web"
    if target.exists():
        raise SystemExit(f"{target} already exists; choose a fresh --output directory.")
    target.mkdir()
    source = ROOT / "apps/web"
    for name in ("app", "components", "lib", "public"):
        directory = source / name
        if directory.exists():
            shutil.copytree(directory, target / name,
                            ignore=shutil.ignore_patterns(".env*", "*.test.*", "node_modules", ".next"))
    for name in ("package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml", "tsconfig.json",
                 "next.config.ts", "next-env.d.ts", "postcss.config.mjs"):
        shutil.copy2(source / name, target / name)
    assert not any(p.name.startswith(".env") for p in target.rglob("*"))
    archive = output / "call-grader-frontend.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for path in sorted(target.iterdir()):
            tar.add(path, arcname=path.name)
    print(f"Appwrite Sites source: {target}")
    print(f"Frontend archive: {archive}")


if __name__ == "__main__":
    main()
