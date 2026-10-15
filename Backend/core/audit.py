"""Two append-only audit logs: one technical, one business.

Plain text, one event per line, appended forever - no rotation by design, so "the log" is
always a single file an admin can download or `tail -f` during the conference.

    technical  credentials and accounts: logins, registrations, hash issuing and dropping,
               hash reveals, database setup.
    business   what happened at the conference: papers submitted and graded, awards
               assigned, announcements, checklists and the timeline being changed.

Call sites use the two helpers rather than touching loggers, because the interesting part
is the domain detail, not the transport:

    audit.technical("login.failed", hash=audit.masked(typed), reason="bad_password")
    audit.business("grade.saved", actor=audit.actor(user), delegate=42, total="15/17.5")

What belongs in which log, and the rule that no access code is ever written in full (use
`masked`), are conventions this module cannot enforce - they are documented here and at
each call site.

Writes are made through the standard library's logging, which locks per write and swallows
its own errors, so a full disk or an unwritable directory degrades the audit trail instead
of failing a request.
"""

import logging
import os
import time
from pathlib import Path
from typing import Any

# The storage root, following the same pattern as PAPER_UPLOAD_DIR: a repo-local default
# for development, overridden on the server (e.g. LOG_DIR=/var/log/scvmun).
DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"

FILES = {"technical": "technical.log", "business": "business.log"}
LOGGERS = {"technical": "scvmun.technical", "business": "scvmun.business"}

# Which directory the handlers are currently attached to, so tests (and anything that
# moves LOG_DIR) can reconfigure simply by changing the environment.
_configured_for: Path | None = None


def log_dir() -> Path:
    """The directory holding the log files. Not created - see configure()."""
    return Path(os.getenv("LOG_DIR") or DEFAULT_LOG_DIR)


def log_path(kind: str) -> Path:
    """Path of one log file."""
    return log_dir() / FILES[kind]


def configure() -> None:
    """Attach a file handler per log, creating the directory and files if needed.

    Idempotent per directory. If the directory cannot be created or a file cannot be
    opened, that logger falls back to stderr rather than dropping the line or raising:
    logging is never the reason a request fails. The fallback is sticky for that
    directory, so a broken location does not retry a failing mkdir on every event.
    """
    global _configured_for

    target = log_dir()
    if _configured_for == target:
        return

    for logger in (logging.getLogger(name) for name in LOGGERS.values()):
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass  # each handler below falls back to stderr

    for kind, name in LOGGERS.items():
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # keep audit lines out of any root/uvicorn handler

        try:
            path = log_path(kind)
            # touch() will not tighten an existing file's mode, so chmod explicitly: the
            # technical log holds masked fragments of credentials and is admin-only.
            path.touch(mode=0o600, exist_ok=True)
            os.chmod(path, 0o600)
            handler: logging.Handler = logging.FileHandler(path, encoding="utf-8")
        except OSError:
            handler = logging.StreamHandler()

        formatter = logging.Formatter(
            "%(asctime)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ"
        )
        formatter.converter = time.gmtime  # %(asctime)s is local time by default
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _configured_for = target


def actor(user: Any) -> str:
    """Render the caller as `role:id`, which is stable across renames.

    Anything without both attributes (None, a CLI script) renders as `-` rather than as
    the string "None", which would read like a user called None in the log.
    """
    if user is None:
        return "-"
    role = getattr(user, "role", None)
    identifier = getattr(user, "id", None)
    if role is None or identifier is None:
        return str(user)
    return f"{role}:{identifier}"


def masked(value: str | None) -> str:
    """A recognisable fragment of an access code, never the usable value.

    Four characters are enough to correlate "the code starting AB12" with an account or a
    reissued hash, and leave the code itself out of a file that gets downloaded.
    """
    text = (value or "").strip()
    if not text:
        return "-"
    if len(text) <= 4:
        return f"{text}…"
    return f"{text[:4]}…({len(text)})"


def short(text: str | None, limit: int = 60) -> str:
    """Truncate a human-written value (a broadcast line, a comment) for one log line."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1] + "…"


def technical(action: str, **fields: Any) -> None:
    """Write one line to the technical log."""
    _emit("technical", action, fields)


def business(action: str, **fields: Any) -> None:
    """Write one line to the business log."""
    _emit("business", action, fields)


def read(kind: str) -> str:
    """The log's contents, or "" when nothing has been written yet."""
    try:
        return log_path(kind).read_text(encoding="utf-8")
    except OSError:
        return ""


def _emit(kind: str, action: str, fields: dict[str, Any]) -> None:
    configure()
    rendered = " ".join(f"{key}={_render(value)}" for key, value in fields.items())
    logging.getLogger(LOGGERS[kind]).info(f"{action} {rendered}".rstrip())


def _render(value: Any) -> str:
    """One `key=value` value: no spaces, so a line stays greppable and splittable."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"

    text = str(value)
    if not text:
        return "-"
    if any(character.isspace() for character in text) or '"' in text:
        return '"' + text.replace('"', '\\"') + '"'
    return text
