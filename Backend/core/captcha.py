"""Cloudflare Turnstile verification for the pre-auth routes.

The widget in the browser produces a single-use token, valid for 300 seconds; only
Cloudflare can say whether it is genuine, so the token is posted to Siteverify and the
answer decides whether `/auth/login` and `/auth/register` run at all.

Two environment variables:

    TURNSTILE_SECRET       the widget's secret. When it is empty the check is disabled
                           (development, tests) and every request passes - the app logs a
                           warning at startup so that cannot happen unnoticed in production.
    TURNSTILE_HOSTNAMES    comma-separated allow-list checked against the `hostname`
                           Siteverify reports. REQUIRED whenever the secret is set: with an
                           empty list we reject every token, because otherwise any hostname
                           Cloudflare reports would pass.

Production must list only the real frontend hostname(s); localhost/127.0.0.1 belong in a
development deployment's value, never in production's.

Why hand-rolled instead of a client library: this is one form-encoded POST with a JSON
reply, so `urllib` keeps the dependency list unchanged - the same reason the rest of the
backend avoids a Redis client, an HTTP client, and a captcha SDK.
"""

import json
import os
from typing import Any, Final
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SITEVERIFY_URL: Final = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def secret_key() -> str:
    """The widget's secret, read from the environment **at call time**.

    Deliberately not a module-level constant. This module is imported very early - through
    `API/dependencies.py`, before any `crud.*` module - and `load_dotenv()` only runs when
    `crud/db.py` is imported. A constant captured at import time therefore read an empty
    environment, `enabled()` returned False, and the startup log reported
    `captcha.disabled` with no other symptom: logins simply stopped asking for a token.
    Reading it here makes the answer independent of import order.
    """
    return os.getenv("TURNSTILE_SECRET", "").strip()


def allowed_hostnames() -> tuple[str, ...]:
    """The hostnames Siteverify may report, read at call time for the same reason.

    Empty means "reject everything" once the secret is set (see `verify`).
    """
    return tuple(
        host.strip().lower()
        for host in os.getenv("TURNSTILE_HOSTNAMES", "").split(",")
        if host.strip()
    )

# The gate should answer quickly; Cloudflare is not on the critical path of a normal
# request, only of a login attempt.
TIMEOUT_SECONDS: Final = 5.0

# The action the widget is rendered with, echoed back by Siteverify. One widget serves the
# whole auth screen (both buttons), so there is one action rather than one per endpoint;
# keep it in step with `action: "auth"` in LoginRegisterView.vue.
ACTION: Final = "auth"

# Siteverify's documented maximum. Rejecting a longer string locally saves a round trip and
# keeps a hostile client from making us post megabytes.
MAX_TOKEN_LENGTH: Final = 2048


class CaptchaUnavailable(RuntimeError):
    """Verification could not be completed: network down, timeout, or a garbled reply.

    Kept distinct from "the token is invalid" so the route can answer 503 ("try again")
    rather than telling a legitimate user their human check failed.
    """


def enabled() -> bool:
    """Whether a captcha is configured at all."""
    return bool(secret_key())


def verify(
    token: str | None,
    remote_ip: str | None = None,
    expected_action: str = ACTION,
) -> bool:
    """Ask Cloudflare whether `token` is genuine for this action and hostname.

    Returns False for a missing, over-long, expired, reused or forged token, for a token
    minted for a different action, and for a token minted on a hostname outside the
    allow-list. Raises CaptchaUnavailable when the answer could not be obtained, so the
    caller can fail closed with an honest message instead of blaming the visitor.
    """
    if not enabled():
        return True

    # Fail closed on a half-done deployment: with no expected hostnames there is nothing to
    # compare against, and accepting any hostname would make the check theatre.
    hostnames = allowed_hostnames()
    if not hostnames:
        return False

    if not token or len(token) > MAX_TOKEN_LENGTH:
        return False

    form = {"secret": secret_key(), "response": token}
    if remote_ip:
        form["remoteip"] = remote_ip

    request = Request(
        SITEVERIFY_URL,
        data=urlencode(form).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            payload: Any = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        # OSError covers connection failures, timeouts and non-2xx replies (HTTPError is a
        # URLError is an OSError); ValueError covers a body that is not JSON.
        raise CaptchaUnavailable(str(exc)) from exc

    if not isinstance(payload, dict) or payload.get("success") is not True:
        return False

    reported = str(payload.get("hostname") or "").lower()
    if reported not in hostnames:
        return False

    if expected_action and str(payload.get("action") or "") != expected_action:
        return False

    return True
