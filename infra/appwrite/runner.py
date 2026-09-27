"""Subprocess entrypoint for bounded synchronous Function workloads."""

import json
import sys
from types import SimpleNamespace

from infra.appwrite.common import invocation, runtime_check


def main():
    request = json.load(sys.stdin)
    context = SimpleNamespace(req=SimpleNamespace(headers=request["headers"]))
    with invocation(context):
        if request["body"].get("action") == "runtime-check":
            result = runtime_check()
        else:
            from app.functions.pipeline import run_maintenance, run_sync, run_worker

            handlers = {"worker": run_worker, "sync": lambda: run_sync(request["body"]),
                        "maintenance": run_maintenance}
            result = handlers[request["role"]]()
        print("FUNCTION_RESULT=" + json.dumps(result))


if __name__ == "__main__":
    main()
