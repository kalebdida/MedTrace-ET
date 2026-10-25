"""HTTP transport for the unchanged Lambda routing and verification logic."""

import os
from pathlib import Path
import threading
from collections import Counter, deque
from functools import lru_cache
import jwt
import numpy as np
from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
import app
from medtrace import metrics

api = FastAPI(docs_url=None, redoc_url=None)
counts = Counter()
latencies = deque(maxlen=10000)
lock = threading.Lock()
_original_emit = metrics.emit


def emit(namespace, values, dimensions, properties=None):
    with lock:
        for name, value, _ in values:
            if name == "ScanLatency":
                latencies.append(value)
            else:
                counts[name] += value
    _original_emit(namespace, values, dimensions, properties)


metrics.emit = emit


@lru_cache(maxsize=4)
def jwks(url):
    return jwt.PyJWKClient(url, timeout=5)


def claims(token):
    try:
        url = os.environ["SUPABASE_URL"].rstrip("/")
        algorithm = jwt.get_unverified_header(token).get("alg")
        if algorithm == "HS256":
            key = os.environ["SUPABASE_JWT_SECRET"]
        elif algorithm in ("RS256", "ES256"):
            key = (
                jwks(url + "/auth/v1/.well-known/jwks.json")
                .get_signing_key_from_jwt(token)
                .key
            )
        else:
            return None
        verified = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience="authenticated",
            issuer=url + "/auth/v1",
            options={"require": ["exp", "sub", "aud", "iss"]},
        )
        result = {"sub": verified["sub"]}
        site = verified.get("app_metadata", {}).get("site_id")
        if isinstance(site, str) and site:
            result["custom:site_id"] = site
        return result
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        return None


@api.get("/metrics")
def snapshot():
    with lock:
        return {
            **{
                k: counts[k]
                for k in [
                    "ScansProcessed",
                    "CloneAlerts",
                    "InvalidBarcodes",
                    "VisualMismatches",
                    "VisualCheckErrors",
                ]
            },
            "latency_p50_ms": float(np.percentile(latencies, 50))
            if latencies
            else None,
            "latency_p95_ms": float(np.percentile(latencies, 95))
            if latencies
            else None,
        }


@api.api_route(
    "/{path:path}", methods=["GET", "POST", "OPTIONS", "PUT", "DELETE", "PATCH"]
)
async def bridge(request: Request, path: str):
    auth = request.headers.get("authorization", "")
    verified = (
        await run_in_threadpool(claims, auth[7:])
        if auth.lower().startswith("bearer ")
        else None
    )
    if (
        request.method != "OPTIONS"
        and request.url.path in ("/scan", "/history")
        and not verified
    ):
        return Response(
            '{"error":"Sign-in required"}',
            status_code=401,
            media_type="application/json",
        )
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 2_200_000:
            return Response(status_code=413)
    import base64

    event = {
        "version": "2.0",
        "rawPath": request.url.path,
        "headers": dict(request.headers),
        "queryStringParameters": dict(request.query_params),
        "body": base64.b64encode(body).decode(),
        "isBase64Encoded": True,
        "requestContext": {
            "http": {"method": request.method, "path": request.url.path},
            "stage": "$default",
        },
    }
    if verified:
        event["requestContext"]["authorizer"] = {"jwt": {"claims": verified}}
    result = await run_in_threadpool(app.lambda_handler, event, None)
    revision = Path(__file__).with_name("deployment_revision.txt")
    if revision.exists():
        result.setdefault("headers", {})["X-Deployment-Revision"] = (
            revision.read_text().strip()
        )
    return Response(
        result.get("body", ""),
        status_code=result["statusCode"],
        headers=result.get("headers", {}),
    )
