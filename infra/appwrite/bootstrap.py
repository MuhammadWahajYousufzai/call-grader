"""One-time private schema provisioning Function."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from infra.appwrite.common import invocation


def main(context):
    with invocation(context):
        from app.appwrite import client as aw

        from scripts import bootstrap_appwrite

        # Reuse the invocation's scoped credential; never persist it in env.
        bootstrap_appwrite._client = aw.get_client
        bootstrap_appwrite.main(function_execution=True)
        context.log('FUNCTION_RESULT_JSON={"status":"SUCCESS"}')
        return context.res.json({"status": "SUCCESS"})
