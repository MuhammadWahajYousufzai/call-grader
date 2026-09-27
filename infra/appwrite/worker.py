"""Appwrite worker entrypoint."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from infra.appwrite.common import run_child


async def main(context):
    return await run_child(context, "worker")
