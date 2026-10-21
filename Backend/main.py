"""
SCVMUN Platform API entry point.

Run from the Backend/ directory so the `API` and `schemas` packages resolve:

    uvicorn main:app --reload

Interactive docs (generated from the response models) are at /docs.
"""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from API.endpoints import api_router
import core.audit
import core.captcha
import core.monitor

API_PREFIX = "/api"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the downtime monitor for exactly as long as the API is serving.

    Started here rather than at import so tests do not spawn threads or write heartbeat
    files, and stopped on shutdown so --reload does not leave one behind.
    """
    if not core.captcha.enabled():
        # Not fatal - development and the test suite run this way - but a deployment that
        # forgot the key would otherwise be silently open, so it goes in the log an admin
        # actually reads.
        core.audit.technical(
            "captcha.disabled",
            hint="set TURNSTILE_SECRET to require the human check on login and register",
        )
    elif not core.captcha.ALLOWED_HOSTNAMES:
        # Fail-closed is the right default, but it means every login is rejected, so say so
        # at startup rather than leaving it to the first confused delegate.
        core.audit.technical(
            "captcha.misconfigured",
            hint="TURNSTILE_HOSTNAMES is empty, so every login and registration will be rejected",
        )

    core.monitor.start()
    try:
        yield
    finally:
        core.monitor.stop()


app = FastAPI(
    title="SCVMUN Platform API",
    description="Backend for the SCVMUN conference platform. See Frontend-API-Contract.md.",
    lifespan=lifespan,
)


# --- CORS ---
# The Vite dev server and this API run on different origins, so the browser needs an
# explicit allow-list. Override with CORS_ALLOW_ORIGINS="https://a.com,https://b.com".
_origins = os.getenv(
    "CORS_ALLOW_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Error shape ---
# The frontend reads `error.response.data.message` (Frontend/src/api/client.js), so every
# error path is normalised to {"message": "..."} instead of FastAPI's default
# {"detail": ...}. Without these handlers the UI would only ever show "Server Error (NNN)".


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Keep the handler's own headers: without this a 429's Retry-After (and a 401's
    # WWW-Authenticate) would be silently dropped on the way out.
    return JSONResponse(
        status_code=exc.status_code,
        content={"message": exc.detail},
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Collapse Pydantic's error list into a single human-readable message."""
    errors = exc.errors()
    if not errors:
        return JSONResponse(status_code=422, content={"message": "Invalid request."})

    first = errors[0]
    location = ".".join(
        str(part) for part in first.get("loc", []) if part not in ("body", "query", "path")
    )
    detail = first.get("msg", "Invalid request.")
    message = f"{location}: {detail}" if location else detail

    return JSONResponse(status_code=422, content={"message": message})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"message": "Internal server error."})


# --- Routes ---
# Every route group lives under /api, matching the frontend's axios baseURL.
app.include_router(api_router, prefix=API_PREFIX)


@app.get("/", tags=["meta"])
def root() -> dict[str, str]:
    """Convenience landing route; not part of the frontend contract."""
    return {"message": "SCVMUN Platform API", "docs": "/docs"}
