"""Bridge Appwrite execution requests to the existing private FastAPI API."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from infra.appwrite.common import invocation


async def main(context):
    import httpx

    with invocation(context):
        from app.main import app

        path = context.req.path
        if context.req.query_string:
            path += "?" + context.req.query_string
        # SDK infrastructure credentials never reach application routes.
        headers = {key: value for key, value in context.req.headers.items()
                   if key.lower() in ("content-type", "x-internal-token", "x-actor")}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                    base_url="http://function") as client:
            try:
                response = await client.request(context.req.method, path, headers=headers,
                                                content=context.req.body_binary)
            except Exception as exc:
                context.error(f"API service failed: {type(exc).__name__}: {exc}")
                return context.res.json({"error": "Backend service unavailable"}, 503)
        return context.res.text(response.text, response.status_code,
                                {"content-type": response.headers.get("content-type", "application/json")})
