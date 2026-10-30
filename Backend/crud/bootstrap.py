"""First-run setup: the schema, the first admin, and the schools.

    python -m crud.bootstrap --admin-name "Ethan Santiago"
    python -m crud.bootstrap --admin-name "Ethan" --schools ../deploy/schools.example.json
    docker compose run --rm api python -m crud.bootstrap --admin-name "Ethan" ...

Why this exists, and why it is not part of `seed.py`: `seed.py` creates the tables and
nothing else, which is safe to re-run forever. Filling in *rows* is not - inserting an
admin or a school twice is a different outcome - so that step lives here, guarded, and
reuses `seed.ensure_schema()` for the DDL rather than reimplementing it.

What it creates:

* every missing table;
* one `admin` account with `password_hash = NULL`. Claim it through the login screen's
  "First-Time Register" using the access code printed at the end. Nothing secret is stored
  by this script and no password is invented;
* one advisor account plus one `School` per entry in the `--schools` file.

Schools are here because nothing else can create them: `POST /admin/hashes` needs an
existing school (`_get_school` 404s otherwise) and no endpoint inserts one. Committees are
*not* needed - `_ensure_committee` creates them when hashes are minted - and the checklist
and timeline are both editable from the admin UI.

Idempotent: an existing admin is never replaced, an existing school is never touched, and
no password is ever reset. Re-running after adding a school to the file only adds that
school. Access codes are printed once per *creation*; if one is lost, read it back with
`SELECT name, identifier FROM accounts WHERE role = 'advisor';`.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# Allow `python crud/bootstrap.py` as well as `python -m crud.bootstrap`; see crud/seed.py
# for why a directly-run script needs Backend/ on sys.path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

import core.audit

import crud.onboarding as onboarding
from crud.database_schema import Account, School
from crud.db import DATABASE_URL, SessionLocal, engine
from crud.seed import ensure_schema

# Shared with POST /admin/schools, so a school created here and a school created through the
# API cannot differ. Named locally for the messages below.
SCHOOL_FIELDS = onboarding.SCHOOL_FIELDS
PAYMENT_STATUSES = onboarding.PAYMENT_STATUSES


def mint_hash() -> str:
    """A new access code, in the same format the admin endpoints mint."""
    return onboarding.mint_hash()


def load_schools(path: Path) -> list[dict[str, Any]]:
    """Read and validate the schools file, failing with a message that can be acted on."""
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SystemExit(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON: {exc}") from exc

    if not isinstance(entries, list):
        raise SystemExit(f"{path} must contain a JSON array of school objects.")

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise SystemExit(f"Entry {index} in {path} is not an object.")
        missing = [field for field in SCHOOL_FIELDS if not str(entry.get(field, "")).strip()]
        if missing:
            raise SystemExit(
                f"Entry {index} in {path} is missing: {', '.join(missing)}."
            )
        status = entry.get("payment_status", "unpaid")
        if status not in PAYMENT_STATUSES:
            raise SystemExit(
                f"Entry {index} in {path} has payment_status {status!r}; "
                f"use one of: {', '.join(PAYMENT_STATUSES)}."
            )

    return entries


def ensure_admin(db, name: str, identifier: str | None) -> tuple[str | None, str | None]:
    """Create the first admin if there is none. Returns (identifier, message)."""
    existing = db.scalars(select(Account).where(Account.role == "admin")).first()
    if existing is not None:
        # Deliberately not touching it: an admin's password may already be set, and
        # rotating someone's credentials from a bootstrap script is not this script's job.
        return None, f"admin already exists ({existing.name}); left untouched"

    code = identifier or mint_hash()
    db.add(Account(identifier=code, role="admin", name=name))
    return code, None


def ensure_school(db, entry: dict[str, Any]) -> tuple[str | None, str]:
    """Create the advisor account and school row if absent. Returns (identifier, message)."""
    school_name = str(entry["school_name"]).strip()
    existing = db.scalars(select(School).where(School.school_name == school_name)).first()
    if existing is not None:
        return None, "already present"

    missing = onboarding.missing_fields(entry)
    if missing:
        raise SystemExit(f"School {school_name!r} is missing: {', '.join(missing)}.")

    # The same helper POST /admin/schools uses, so both produce identical rows.
    advisor, _school = onboarding.create_school_with_advisor(db, values=entry)
    return advisor.identifier, "created"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the schema, the first admin, and the schools.",
    )
    parser.add_argument(
        "--admin-name",
        required=True,
        help='display name for the first admin, e.g. "Ethan Santiago"',
    )
    parser.add_argument(
        "--admin-hash",
        default=None,
        help="access code for the admin (default: a random one, printed once)",
    )
    parser.add_argument(
        "--schools",
        type=Path,
        default=None,
        help="JSON array of schools to create (see deploy/schools.example.json)",
    )
    args = parser.parse_args()

    if not DATABASE_URL:
        raise SystemExit(
            "DATABASE_URL is not set. Add it to Backend/crud/.env (see crud/db.py)."
        )

    target = engine.url.render_as_string(hide_password=True)
    print(f"Target database: {target}")

    tables = ensure_schema(engine)
    print(f"Schema ready: {len(tables)} tables.")

    schools = load_schools(args.schools) if args.schools else []
    if not schools:
        print(
            "No --schools given. Note that hashes cannot be minted for a school that does "
            "not exist yet."
        )

    admin_code: str | None = None
    admin_note: str | None = None
    created: list[tuple[str, str, str]] = []

    db = SessionLocal()
    try:
        admin_code, admin_note = ensure_admin(db, args.admin_name, args.admin_hash)

        for entry in schools:
            # The third element is the new advisor code, or "already present" - the two
            # outcomes the report separates.
            code, note = ensure_school(db, entry)
            created.append((str(entry["school_name"]), str(entry["advisor_name"]), code or note))

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print()
    if admin_code is not None:
        print("Admin access code (claim it with \"First-Time Register\"):")
        print(f"  {args.admin_name}: {admin_code}")
    else:
        print(f"Admin: {admin_note}.")

    if created:
        print()
        print("Schools:")
        for school_name, advisor_name, detail in created:
            if detail == "already present":
                print(f"  {school_name} ({advisor_name}): already present, untouched")
            else:
                print(f"  {school_name} ({advisor_name}): advisor code {detail}")
        if any(detail != "already present" for _, _, detail in created):
            print()
            print("Give each advisor their code; they claim it with \"First-Time Register\".")
            print("These codes are printed once. If one is lost:")
            print("  SELECT name, identifier FROM accounts WHERE role = 'advisor';")

    # Logged only where the API's log directory already exists, same reasoning as
    # crud/seed.py: a root-owned log file would then be unwritable by the API.
    if core.audit.log_dir().is_dir():
        core.audit.technical(
            "bootstrap.completed",
            admin=bool(admin_code),
            schools=sum(1 for entry in created if entry[2] != "already present"),
        )


if __name__ == "__main__":
    main()
