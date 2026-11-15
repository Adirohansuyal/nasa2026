"""Small server-side OpenRouter proxy for the static EARTHPULSE-X site."""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque

from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

load_dotenv()

_WINDOW_SECONDS = 60
_MAX_REQUESTS_PER_WINDOW = 12
_MAX_PROMPT_CHARS = 12_000
_request_times: dict[str, deque[float]] = defaultdict(deque)


async def health(_: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "service": "earthpulse-explainer"})


async def explain(request: Request) -> JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = _request_times[client_ip]
    while recent and now - recent[0] > _WINDOW_SECONDS:
        recent.popleft()
    if len(recent) >= _MAX_REQUESTS_PER_WINDOW:
        return JSONResponse({"error": "Too many explanation requests. Please wait a minute."}, status_code=429)
    recent.append(now)

    if request.headers.get("content-length", "0").isdigit() and int(request.headers["content-length"]) > 16_000:
        return JSONResponse({"error": "The explanation context is too large."}, status_code=413)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "Send a JSON object containing a prompt."}, status_code=400)
    prompt = payload.get("prompt") if isinstance(payload, dict) else None
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > _MAX_PROMPT_CHARS:
        return JSONResponse({"error": "The explanation prompt is missing or too long."}, status_code=400)

    try:
        from core.openrouter_client import explain_text

        answer = await run_in_threadpool(
            explain_text,
            prompt.strip(),
            500,
            "You explain Earth observation statistics to the public. Use only supplied evidence. "
            "Never claim correlation proves causation, never invent measurements, and clearly state "
            "when evidence is weak, mixed, or insufficient. Write in clear, concise Hinglish when asked.",
        )
    except RuntimeError as exc:
        if "OPENROUTER_API_KEY" in str(exc):
            return JSONResponse({"error": "OpenRouter is not configured on the server."}, status_code=503)
        return JSONResponse({"error": "The explanation service is not configured."}, status_code=503)
    except Exception:
        return JSONResponse({"error": "OpenRouter could not generate an explanation right now."}, status_code=502)
    return JSONResponse({"answer": answer})


allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "EARTHPULSE_ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:8000,http://127.0.0.1:8000",
    ).split(",")
    if origin.strip()
]

app = Starlette(routes=[Route("/health", health, methods=["GET"]), Route("/api/explain", explain, methods=["POST"])])
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
    max_age=600,
)
