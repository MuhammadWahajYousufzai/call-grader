"""Lightweight hourly watchdog; discovery owns the browser and date checkpoints."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from infra.appwrite.common import invocation, request_body


def main(context):
    try:
        body = request_body(context)
    except ValueError:
        return context.res.json({"error": "JSON object required"}, 400)
    with invocation(context):
        from app.appwrite import client as aw
        from app.appwrite import repos
        from app.functions.pipeline import dispatch
        from appwrite.services.functions import Functions

        target = os.environ["APPWRITE_SYNC_FUNCTION_ID"]
        if body.get("action") == "runtime-check":
            # Exercise the same private execution permission as the watchdog,
            # while the already-warm discovery runtime checks its native tools.
            execution = repos._as_dict(Functions(aw.get_client()).create_execution(
                function_id=target, body=json.dumps(body), xasync=False))
            if execution.get("responseStatusCode") != 200:
                raise RuntimeError("Discovery runtime verification failed")
            result = json.loads(execution["responseBody"])
        else:
            execution = dispatch(target)
            result = {"status": "DISPATCHED", "execution_id": execution["$id"]}
        context.log(json.dumps(result))
        return context.res.json(result)
