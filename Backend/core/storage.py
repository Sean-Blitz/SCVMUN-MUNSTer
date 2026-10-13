"""Where uploaded position papers live on disk.

Papers are kept on the server's filesystem, not in Postgres: the `position_papers`
table holds the metadata and the *relative* path only, so the storage root can move
(or the database be pointed elsewhere) without rewriting rows.

Two environment variables tune this:

    PAPER_UPLOAD_DIR   storage root. Defaults to Backend/crud/pdf_uploads for
                       development; on the Ubuntu box point it somewhere outside the
                       repo, e.g. /var/lib/scvmun/papers, so a redeploy cannot wipe it.
    PAPER_MAX_MB       largest accepted upload, in MB (default 10).

Nothing here trusts the client's filename. A paper is stored under a generated name
and the original is kept in `position_papers.file_name` for display only, which is what
keeps a name like "../../etc/passwd" from becoming a path.
"""

import os
import secrets
from pathlib import Path

# Backend/crud/pdf_uploads, resolved from this file rather than from the cwd, so it
# works no matter which directory uvicorn was started from.
DEFAULT_UPLOAD_DIR = Path(__file__).resolve().parents[1] / "crud" / "pdf_uploads"

MAX_PAPER_BYTES = int(os.getenv("PAPER_MAX_MB", "10")) * 1024 * 1024


def upload_dir() -> Path:
    """The configured storage root. Not created - reads use this, writes use ensure_upload_dir."""
    return Path(os.getenv("PAPER_UPLOAD_DIR") or DEFAULT_UPLOAD_DIR)


def ensure_upload_dir() -> Path:
    """The storage root, created if it is not there yet. Writing needs this."""
    root = upload_dir()
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_paper_name(delegate_id: int) -> str:
    """A fresh, unguessable file name for one delegate's paper.

    Generated rather than derived from the upload, so two delegates submitting
    "paper.pdf" cannot collide and no client input reaches the path.
    """
    return f"delegate-{delegate_id}-{secrets.token_hex(16)}.pdf"


def paper_path(relative_path: str) -> Path:
    """Absolute path for a stored paper, refusing anything outside the storage root."""
    root = upload_dir().resolve()
    path = (root / relative_path).resolve()
    if root not in path.parents:
        raise ValueError(f"Refusing a path outside the upload directory: {relative_path!r}")
    return path


def save_paper(relative_path: str, data: bytes) -> None:
    """Write a paper atomically: a half-written file must never look complete.

    The bytes go to a sibling `.part` file first and are fsynced, then the rename swaps
    them in. `os.replace` is atomic within one filesystem, which is why the temporary
    file sits next to the target rather than in /tmp.

    The file is created 0600 (owner only): position papers are not public, and this way
    the contents stay private even if the directory's own mode is widened later.
    """
    ensure_upload_dir()
    target = paper_path(relative_path)
    part = target.with_suffix(target.suffix + ".part")
    try:
        descriptor = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(part, target)
    except OSError:
        part.unlink(missing_ok=True)
        raise


def delete_paper(relative_path: str) -> None:
    """Remove a stored paper.

    Used to undo a write when the matching database row never landed, and by any future
    route that drops a delegate. Best-effort: a missing file is not an error.
    """
    try:
        paper_path(relative_path).unlink(missing_ok=True)
    except (OSError, ValueError):
        pass
