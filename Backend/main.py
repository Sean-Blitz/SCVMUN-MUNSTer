"""
SCVMUN Platform API entry point.

Run from the Backend/ directory so the `API` and `schemas` packages resolve:

    uvicorn main:app --reload

Interactive docs (generated from the response models) are at /docs.
"""

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from API.endpoints import api_router
import core.audit
import core.captcha
import core.monitor
from crud.db import get_db

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


def _field_label(loc: tuple) -> str:
    """Turn Pydantic's `loc` into something a delegate can act on.

    `("body", "advisor_phone")` becomes "advisor phone"; a nested entry such as
    `("body", "finalAssignments", "1", 0)` becomes "finalAssignments (entry 1)", so the
    admin knows which row to fix.
    """
    # Strip only the *leading* context tag, and only when something follows it: a field
    # genuinely named "body" (BroadcastRequest has one) must not be swallowed, and
    # `loc` is ("body", "body") through FastAPI but ("body",) when a model is validated
    # on its own.
    prefixed = len(loc) > 1 and loc[0] in ("body", "query", "path", "header")
    parts = list(loc[1:]) if prefixed else list(loc)
    named = [p for p in parts if isinstance(p, str) and not p.isdigit()]
    numbers = [p for p in parts if isinstance(p, int) or (isinstance(p, str) and p.isdigit())]

    label = named[-1].replace("_", " ") if named else "request"
    if numbers:
        entry = numbers[0] + 1 if isinstance(numbers[0], int) else numbers[0]
        label = f"{label} (entry {entry})"
    return label


def _friendly_message(error: dict) -> str:
    """One Pydantic error as a sentence. This string is shown in a toast, verbatim."""
    kind = error.get("type", "")
    context = error.get("ctx") or {}
    field = _field_label(tuple(error.get("loc", ())))

    if kind == "string_too_long":
        return f"{field} must be at most {context.get('max_length')} characters"
    if kind == "string_too_short":
        return f"{field} must be at least {context.get('min_length')} characters"
    if kind in ("too_long", "list_too_long"):
        return f"{field} has too many items (at most {context.get('max_length')})"
    if kind in ("too_short", "list_too_short"):
        return f"{field} needs at least {context.get('min_length')} items"
    if kind == "missing":
        return f"{field} is required"
    if kind.startswith("datetime"):
        return f"{field} must be an ISO-8601 timestamp"
    if kind in ("literal_error", "enum"):
        return f"{field} must be one of: {context.get('expected')}"
    if kind.endswith("_type"):
        return f"{field} is not a valid value"
    return f"{field}: {error.get('msg', 'invalid value')}"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Collapse Pydantic's error list into one human-readable message.

    The frontend puts `message` straight into a toast (src/api/client.js), so these read
    as sentences rather than as `body.advisor_phone: String should have at most ...`.
    Up to three problems are reported at once, because fixing a form one field per submit
    is worse than one sentence listing them.
    """
    errors = exc.errors()
    if not errors:
        return JSONResponse(status_code=422, content={"message": "Invalid request."})

    messages = [_friendly_message(error) for error in errors[:3]]
    if len(errors) > 3:
        messages.append(f"and {len(errors) - 3} more")
    # One capital at the start and one full stop at the end: the parts are clauses of a
    # single sentence, which is what reads well in a toast.
    message = "; ".join(messages)

    return JSONResponse(
        status_code=422,
        content={"message": message[0].upper() + message[1:] + "."},
    )


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


@app.get("/healthz", tags=["meta"])
def healthz(db: Session = Depends(get_db)) -> dict[str, str]:
    """Liveness probe for the container healthcheck and an external monitor.

    Deliberately unauthenticated and deliberately not shallow: the API process answering
    while the database is unreachable is the failure a process-only check hides, and it is
    the one that takes a conference down. Reveals nothing beyond up/down.
    """
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Database unavailable."
        ) from None
    return {"status": "ok"}
