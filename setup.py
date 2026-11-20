#!/usr/bin/env python3
"""
SCVMUN Platform setup wizard.

Run from the repository root, on the machine that will host the conference:

    python3 setup.py

What it does, in order, explaining each step as it goes:

  1. Checks the machine is ready: Docker, the compose plugin, the daemon, openssl,
     the compose file and the ports you are about to publish.
  2. Writes `.env` - the only file holding this deployment's secrets and settings -
     asking you about each group and validating the answers.
  3. Puts a TLS certificate in `tls/`: either one you were issued (it assembles and
     verifies the chain) or a self-signed one for testing.
  4. Builds and starts the three containers, waiting until each reports healthy.
  5. Creates the database schema and the first admin, and prints the admin access code.

It is safe to run twice. Existing values become the defaults, `.env` is backed up before
being rewritten, and bootstrap never resets an account that already exists.

Requirements: Linux, Python 3.9 or newer, Docker with the compose plugin, openssl.
Windows and macOS are not supported targets - the script configures a Linux host.

Flags:
    --yes       take the defaults, ask nothing (for scripted installs)
    --dry-run   report what would happen; write no files, run no containers
    -h, --help  this text
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# --------------------------------------------------------------------------------------
# Paths and constants
# --------------------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
COMPOSE_FILE = ROOT / "compose.yaml"

# The order the keys are written in, matching .env.example.
KEY_ORDER = (
    "POSTGRES_PASSWORD",
    "POSTGRES_USER",
    "POSTGRES_DB",
    "VITE_TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET",
    "TURNSTILE_HOSTNAMES",
    "CORS_ALLOW_ORIGINS",
    "SCVMUN_TAG",
    "WEB_PORT",
    "WEB_TLS_PORT",
    "TLS_DIR",
)

# Defaults for anything the user does not answer.
DEFAULTS = {
    "POSTGRES_USER": "scvmun",
    "POSTGRES_DB": "scvmun",
    "SCVMUN_TAG": "local",
    "WEB_PORT": "80",
    "WEB_TLS_PORT": "443",
    "TLS_DIR": "./tls",
    "VITE_TURNSTILE_SITE_KEY": "",
    "TURNSTILE_SECRET": "",
    "TURNSTILE_HOSTNAMES": "",
    "CORS_ALLOW_ORIGINS": "",
}

# Health checks wait this long per service before giving up.
HEALTH_TIMEOUT_SECONDS = 300

OPTIONS = None  # argparse result, set in main()


# --------------------------------------------------------------------------------------
# Small output helpers - the script is a conversation, so the formatting matters
# --------------------------------------------------------------------------------------

WIDTH = 78


def say(text: str = "") -> None:
    print(text)


def rule(char: str = "-") -> None:
    say(char * WIDTH)


def headline(number: int, title: str) -> None:
    say()
    rule("=")
    say(f"STEP {number}: {title}")
    rule("=")


def info(text: str) -> None:
    for line in text.splitlines():
        say(f"  {line}" if line.strip() else "")


def bullet(text: str) -> None:
    info(f"- {text}")


def warn(text: str) -> None:
    say(f"  !  {text}")


def die(message: str, hint: str = "") -> "None":
    say()
    say(f"ERROR: {message}")
    if hint:
        say()
        info(hint)
    say()
    sys.exit(1)


def confirm(question: str, default: bool = True) -> bool:
    """Yes/no question. Defaults are taken without asking when running unattended."""
    if OPTIONS.yes or not sys.stdin.isatty():
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        answer = input(f"  {question} {suffix} ").strip().lower()
        if not answer:
            return default
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False


def interactive() -> bool:
    """True when it is worth asking a human a question.

    `--yes`, or a redirected stdin, mean "take the defaults" rather than "block forever".
    """
    return not OPTIONS.yes and sys.stdin.isatty()


def ask(question: str, default: str = "", secret: bool = False, allow_empty: bool = False) -> str:
    """One answer, with the current/default value shown and re-prompting on a blank required one."""
    if OPTIONS.yes or not sys.stdin.isatty():
        return default

    shown = "" if secret else default
    prompt = f"  {question}"
    if shown:
        prompt += f" [{shown}]"
    elif allow_empty:
        prompt += " [blank]"
    prompt += ": "

    while True:
        if secret:
            answer = getpass.getpass(prompt)
        else:
            answer = input(prompt).strip()
        if not answer:
            answer = default
        if answer or allow_empty:
            return answer
        warn("This one is required.")


# --------------------------------------------------------------------------------------
# .env handling
# --------------------------------------------------------------------------------------


def parse_env(path: Path) -> "dict[str, str]":
    """Read a KEY=VALUE file, ignoring comments and blank lines.

    Deliberately not a full dotenv implementation: this file is written by this script and
    by humans adding a key, so `KEY=value` with optional surrounding quotes is enough.
    """
    values: "dict[str, str]" = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key.startswith("export "):
            key = key[len("export "):].strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def render_env(values: "dict[str, str]") -> str:
    """The .env file's text.

    Comments are written here rather than copied from .env.example, because this file is
    the one an operator opens at 2am - each key says what it is for and what breaks if it
    is wrong.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Written by setup.py on {stamp}. Re-run setup.py to change these safely.",
        "# Docker Compose reads this file for the ${...} substitutions in compose.yaml.",
        "# It is gitignored, and it holds secrets: keep it at mode 600.",
        "",
        "# --- database ---------------------------------------------------------",
        "# POSTGRES_PASSWORD is used twice: the database is created with it, and it is",
        "# interpolated into the API's DATABASE_URL. Characters that are special in a URL",
        "# (@ : / ? #) would break that URL, so setup.py rejects them.",
        f"POSTGRES_PASSWORD={values['POSTGRES_PASSWORD']}",
        f"POSTGRES_USER={values.get('POSTGRES_USER') or DEFAULTS['POSTGRES_USER']}",
        f"POSTGRES_DB={values.get('POSTGRES_DB') or DEFAULTS['POSTGRES_DB']}",
        "",
        "# --- human check (Cloudflare Turnstile) -------------------------------",
        "# Set both or neither. An empty secret disables the check; a secret with an empty",
        "# hostname list rejects EVERY login on purpose. The site key is public and is",
        "# compiled into the frontend at build time.",
        f"VITE_TURNSTILE_SITE_KEY={values.get('VITE_TURNSTILE_SITE_KEY', '')}",
        f"TURNSTILE_SECRET={values.get('TURNSTILE_SECRET', '')}",
        f"TURNSTILE_HOSTNAMES={values.get('TURNSTILE_HOSTNAMES', '')}",
    ]

    if values.get("CORS_ALLOW_ORIGINS"):
        lines += [
            "",
            "# --- optional ---------------------------------------------------------",
            "# Only needed if something calls the API from a different origin. The SPA and",
            "# the API share an origin through nginx, so normally this stays unset.",
            f"CORS_ALLOW_ORIGINS={values['CORS_ALLOW_ORIGINS']}",
        ]
    else:
        lines += ["", "# --- optional ---------------------------------------------------------"]

    lines += [
        "# Image tag for both builds. A version or git sha makes rollbacks one-line.",
        f"SCVMUN_TAG={values.get('SCVMUN_TAG') or DEFAULTS['SCVMUN_TAG']}",
        "",
        "# Host ports to publish. 80 redirects to 443, so both are needed for a public site.",
        f"WEB_PORT={values.get('WEB_PORT') or DEFAULTS['WEB_PORT']}",
        f"WEB_TLS_PORT={values.get('WEB_TLS_PORT') or DEFAULTS['WEB_TLS_PORT']}",
        "",
        "# Where fullchain.pem and privkey.pem live, relative to this file.",
        f"TLS_DIR={values.get('TLS_DIR') or DEFAULTS['TLS_DIR']}",
    ]

    # Anything the operator added themselves is preserved, so a re-run cannot delete it.
    extras = {k: v for k, v in values.items() if k not in KEY_ORDER}
    if extras:
        lines += ["", "# --- keys added outside setup.py -------------------------------------"]
        lines += [f"{key}={value}" for key, value in extras.items()]

    return "\n".join(lines) + "\n"


def write_env(values: "dict[str, str]") -> None:
    if OPTIONS.dry_run:
        info(f"[dry-run] would write {ENV_FILE.name}")
        return

    if ENV_FILE.is_file():
        backup = ENV_FILE.with_name(f".env.backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(ENV_FILE, backup)
        os.chmod(backup, 0o600)
        info(f"Previous .env saved as {backup.name}")

    ENV_FILE.write_text(render_env(values), encoding="utf-8")
    os.chmod(ENV_FILE, 0o600)
    info(f"Wrote {ENV_FILE.name} (mode 600)")


# --------------------------------------------------------------------------------------
# Command helpers
# --------------------------------------------------------------------------------------


def which(program: str) -> "str | None":
    return shutil.which(program)


def run(cmd, capture: bool = True, dry_run_note: str = "") -> subprocess.CompletedProcess:
    """Run a command. In dry-run mode only report it."""
    printable = " ".join(str(part) for part in cmd)
    if OPTIONS.dry_run:
        info(f"[dry-run] {dry_run_note or printable}")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    return subprocess.run(
        cmd,
        cwd=str(ROOT),
        text=True,
        capture_output=capture,
        check=False,
    )


def run_streaming(cmd) -> int:
    """Run a command with its output going straight to the terminal (builds, up, bootstrap)."""
    printable = " ".join(str(part) for part in cmd)
    if OPTIONS.dry_run:
        info(f"[dry-run] {printable}")
        return 0
    say(f"  $ {printable}")
    return subprocess.run(cmd, cwd=str(ROOT), check=False).returncode


def run_capture_streaming(cmd) -> "tuple[int, str]":
    """Stream output as it happens *and* keep a copy, so bootstrap's admin code can be read."""
    printable = " ".join(str(part) for part in cmd)
    if OPTIONS.dry_run:
        info(f"[dry-run] {printable}")
        return 0, ""

    say(f"  $ {printable}")
    collected: "list[str]" = []
    process = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        say(line.rstrip("\n"))
        collected.append(line)
    process.wait()
    return process.returncode, "".join(collected)


def docker_compose(*args, capture: bool = True) -> subprocess.CompletedProcess:
    return run(["docker", "compose", *args], capture=capture)


def port_in_use(port: int) -> bool:
    """True when something already answers on localhost:port.

    A connect() is used rather than bind(): binding 443 needs root, and a non-root bind
    failure would be indistinguishable from the port being taken.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


# --------------------------------------------------------------------------------------
# PEM/tls helpers - all stdlib, with openssl used when it is present
# --------------------------------------------------------------------------------------


def openssl_available() -> bool:
    return which("openssl") is not None


def openssl(*args, stdin_text: "str | None" = None) -> "tuple[int, str]":
    result = subprocess.run(
        ["openssl", *args],
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode, (result.stdout or result.stderr).strip()


def pem_kind(path: Path) -> str:
    """Classify a PEM file by its contents, not its extension.

    Extensions are useless here: a CA delivery mixes .crt and .pem with no consistent
    meaning, and the same file may hold a certificate or a key.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "unreadable"
    if "BEGIN CERTIFICATE REQUEST" in text:
        return "csr"
    if "BEGIN CERTIFICATE" in text:
        return "certificate"
    if "PRIVATE KEY" in text:
        return "private-key"
    return "unknown"


def certificate_blocks(path: Path) -> "list[str]":
    """Every CERTIFICATE block in a file, in order."""
    text = path.read_text(encoding="utf-8", errors="replace")
    pattern = re.compile(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.DOTALL
    )
    return pattern.findall(text)


def cert_field(block: str, field_args) -> str:
    if not openssl_available():
        return ""
    code, out = openssl("x509", "-noout", *field_args, stdin_text=block)
    return out if code == 0 else ""


def cert_identity(block: str) -> "tuple[str, str]":
    """(subject, issuer) for one certificate block."""
    subject = cert_field(block, ["-subject", "-nameopt", "RFC2253"])
    issuer = cert_field(block, ["-issuer", "-nameopt", "RFC2253"])
    subject = subject.split("=", 1)[1].strip() if "=" in subject else subject
    issuer = issuer.split("=", 1)[1].strip() if "=" in issuer else issuer
    return subject, issuer


def cert_expiry(block: str) -> "tuple[str, int]":
    """(end date as text, days remaining). Days is -1 when openssl is unavailable."""
    if not openssl_available():
        return "", -1
    end = cert_field(block, ["-enddate"]).split("=", 1)[-1].strip()
    # openssl prints e.g. "May 26 12:00:00 2027 GMT"; %Z is unreliable across versions, so
    # the trailing zone is dropped and the rest compared as naive UTC.
    parts = end.split()
    days = -1
    if len(parts) >= 5:
        try:
            expires = datetime.strptime(" ".join(parts[:4]), "%b %d %H:%M:%S %Y")
            days = (expires - datetime.now(timezone.utc).replace(tzinfo=None)).days
        except ValueError:
            days = -1
    return end, days


def cert_san_names(block: str) -> "list[str]":
    """DNS names from subjectAltName, plus the CN when there is no SAN."""
    names: "list[str]" = []
    if openssl_available():
        out = cert_field(block, ["-ext", "subjectAltName"])
        names += re.findall(r"DNS:([^,\s]+)", out)
    cn = cert_field(block, ["-subject", "-nameopt", "RFC2253"])
    match = re.search(r"CN=([^,]+)", cn)
    if match:
        names.append(match.group(1).strip())
    return sorted({name for name in names if name})


def public_key_fingerprint(path: Path, kind: str) -> str:
    """Hash of a certificate's or key's public half, for the "do these match" check."""
    if not openssl_available():
        return ""
    if kind == "certificate":
        code, pem = openssl("x509", "-in", str(path), "-noout", "-pubkey")
    else:
        code, pem = openssl("pkey", "-in", str(path), "-pubout")
    if code != 0 or not pem:
        return ""
    return hashlib.sha256(pem.encode()).hexdigest()


def write_tls_files(fullchain_text: str, key_path: Path, tls_dir: Path) -> None:
    if OPTIONS.dry_run:
        info(f"[dry-run] would write {tls_dir / 'fullchain.pem'} and {tls_dir / 'privkey.pem'}")
        return
    tls_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(tls_dir, 0o700)

    fullchain = tls_dir / "fullchain.pem"
    fullchain.write_text(fullchain_text, encoding="utf-8")
    os.chmod(fullchain, 0o644)

    key_out = tls_dir / "privkey.pem"
    shutil.copyfile(key_path, key_out)
    os.chmod(key_out, 0o600)
    info(f"Wrote {fullchain} and {key_out}")


# --------------------------------------------------------------------------------------
# Step 0: preflight
# --------------------------------------------------------------------------------------


def preflight() -> None:
    headline(0, "Checking this machine")

    if sys.platform.startswith("win"):
        die(
            "This script targets Linux. The compose setup works on macOS for development, "
            "but a production install is a Linux host."
        )
    info(f"Repository: {ROOT}")
    info(f"Python: {sys.version.split()[0]}")

    for required in (COMPOSE_FILE, ENV_EXAMPLE):
        if not required.is_file():
            die(
                f"{required.name} is missing from {ROOT}.",
                "Run setup.py from the repository root - the folder that contains "
                "compose.yaml and .env.example.",
            )

    if which("docker") is None:
        die(
            "Docker is not installed.",
            "On Ubuntu:\n"
            "  curl -fsSL https://get.docker.com | sudo sh\n"
            "  sudo usermod -aG docker \"$USER\"      # then log out and back in\n"
            "\n"
            "Then run this script again.",
        )

    version = run(["docker", "compose", "version"])
    if version.returncode != 0:
        die(
            "The Docker Compose plugin is missing.",
            "On Ubuntu:  sudo apt-get install docker-compose-v2\n"
            "This script needs `docker compose` (v2), not the old `docker-compose`.",
        )
    info(f"Docker: {(version.stdout or '').strip()}")

    daemon = run(["docker", "info"])
    if daemon.returncode != 0:
        text = (daemon.stderr or "") + (daemon.stdout or "")
        if "permission denied" in text.lower():
            die(
                "This user cannot talk to the Docker daemon.",
                '  sudo usermod -aG docker "$USER"\n'
                "  # log out and back in, or run: newgrp docker\n"
                "\n"
                "Docker being root-only is the usual cause; this script does not run "
                "docker through sudo because the containers would then be managed by a "
                "different user than the one that rebuilds them later.",
            )
        die(
            "The Docker daemon is not running.",
            "  sudo systemctl enable --now docker",
        )
    info("Docker daemon: reachable")

    if openssl_available():
        info(f"openssl: {openssl('version')[1].splitlines()[0]}")
    else:
        warn(
            "openssl is not installed, so the certificate checks (chain, key match, "
            "expiry) cannot run. Install it with: sudo apt-get install openssl"
        )


# --------------------------------------------------------------------------------------
# Step 1: .env
# --------------------------------------------------------------------------------------


def validate_password(value: str) -> "str | None":
    """Returns a complaint, or None when the value is usable."""
    if len(value) < 12:
        return "Use at least 12 characters - this protects every delegate's data."
    bad = set("@:/?# ") & set(value)
    if bad:
        return (
            "It contains "
            + " ".join(sorted(bad))
            + ", which breaks the DATABASE_URL the API is given. Letters, digits, '-' and '_' only."
        )
    return None


def validate_identifier(value: str) -> "str | None":
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        return "Use lowercase letters, digits and underscores, starting with a letter or underscore."
    return None


def validate_hostnames(value: str) -> "str | None":
    if not value:
        return None
    for host in value.split(","):
        host = host.strip()
        if not host:
            continue
        if "/" in host or ":" in host or " " in host:
            return (
                "Give hostnames only, comma-separated - no scheme, port or trailing slash. "
                "Example: mun.school.edu,localhost"
            )
    return None


def validate_port(value: str) -> "str | None":
    if not value.isdigit() or not 1 <= int(value) <= 65535:
        return "Give a port number between 1 and 65535."
    return None


def ask_validated(question, default, validator, secret=False) -> str:
    """Ask until the answer passes validation, explaining what is wrong each time."""
    while True:
        answer = ask(question, default=default, secret=secret)
        complaint = validator(answer)
        if complaint is None:
            return answer
        warn(complaint)


def step_env(existing: "dict[str, str]") -> "dict[str, str]":
    headline(1, "Configuration (.env)")

    info(
        "Everything this deployment needs is in one file: .env, next to compose.yaml.\n"
        "It is gitignored and readable only by its owner. The values are used twice: to\n"
        "create the database, and as environment variables inside the containers.\n"
        "\n"
        "Press Enter to accept the value in brackets."
    )
    values = dict(existing)

    if ENV_FILE.is_file():
        info("A .env already exists - its values are offered as the defaults, and the\n"
             "file will be backed up before it is rewritten.")
    else:
        info("No .env yet; one will be created.")

    # --- database ---
    say()
    info(
        "DATABASE PASSWORD\n"
        "The PostgreSQL container is created with this password and the API uses it to\n"
        "connect. It never leaves the machine. Leave the prompt blank to generate one."
    )
    current = existing.get("POSTGRES_PASSWORD", "")
    if current:
        info(f"An existing password is set ({len(current)} characters); Enter keeps it.")
        complaint = validate_password(current)
        if complaint:
            warn(f"The stored password will not work: {complaint}")
            warn("Changing it starts a fresh database: the password is set when the data "
                 "volume is first created, so the old volume no longer matches.")
        password = current
    else:
        typed = ask("Database password (blank = generate)", default="", secret=True, allow_empty=True)
        password = typed or secrets.token_urlsafe(24)
        if not typed:
            info(f"Generated a {len(password)}-character password.")
        complaint = validate_password(password)
        while complaint:
            warn(complaint)
            password = ask("Database password", default="", secret=True)
            complaint = validate_password(password)

    values["POSTGRES_PASSWORD"] = password
    values["POSTGRES_USER"] = ask_validated(
        "Database user", existing.get("POSTGRES_USER") or DEFAULTS["POSTGRES_USER"],
        validate_identifier,
    )
    values["POSTGRES_DB"] = ask_validated(
        "Database name", existing.get("POSTGRES_DB") or DEFAULTS["POSTGRES_DB"],
        validate_identifier,
    )

    # --- human check ---
    say()
    info(
        "CLOUDFLARE TURNSTILE (the 'human check' on login and registration)\n"
        "Two values, and they must agree: the site key is compiled into the frontend at\n"
        "build time, the secret is used by the API to verify the token.\n"
        "\n"
        "  both set   -> the check is enforced\n"
        "  both empty -> the check is off (fine for a private test, not for a public site)\n"
        "  secret only, no hostnames -> EVERY login is refused, on purpose\n"
        "\n"
        "The hostname list must contain the exact hostname delegates type, e.g.\n"
        "mun.school.edu - never localhost in production."
    )
    values["VITE_TURNSTILE_SITE_KEY"] = ask(
        "Turnstile site key (blank = disable the check)",
        existing.get("VITE_TURNSTILE_SITE_KEY", "") or DEFAULTS["VITE_TURNSTILE_SITE_KEY"],
        allow_empty=True,
    )
    values["TURNSTILE_SECRET"] = ask(
        "Turnstile secret (blank = disable the check)",
        existing.get("TURNSTILE_SECRET", "") or DEFAULTS["TURNSTILE_SECRET"],
        secret=True,
        allow_empty=True,
    )
    values["TURNSTILE_HOSTNAMES"] = ask_validated(
        "Hostnames for the check, comma-separated",
        existing.get("TURNSTILE_HOSTNAMES") or DEFAULTS["TURNSTILE_HOSTNAMES"],
        validate_hostnames,
    )
    if values["TURNSTILE_SECRET"] and not values["TURNSTILE_HOSTNAMES"]:
        warn(
            "A secret with no hostnames rejects every login. Either add the hostname or "
            "clear the secret."
        )

    # --- ports and tag ---
    say()
    info(
        "PORTS AND VERSION\n"
        f"Port {DEFAULTS['WEB_PORT']} only redirects to HTTPS, so both ports must be free and\n"
        "reachable from the internet once you go live."
    )
    values["WEB_PORT"] = ask_validated(
        "HTTP port", existing.get("WEB_PORT") or DEFAULTS["WEB_PORT"], validate_port
    )
    values["WEB_TLS_PORT"] = ask_validated(
        "HTTPS port", existing.get("WEB_TLS_PORT") or DEFAULTS["WEB_TLS_PORT"], validate_port
    )
    values["SCVMUN_TAG"] = ask(
        "Image tag (a version or git sha makes rollbacks one line)",
        existing.get("SCVMUN_TAG") or DEFAULTS["SCVMUN_TAG"],
    )
    values["TLS_DIR"] = existing.get("TLS_DIR") or DEFAULTS["TLS_DIR"]

    if existing.get("CORS_ALLOW_ORIGINS"):
        values["CORS_ALLOW_ORIGINS"] = existing["CORS_ALLOW_ORIGINS"]

    write_env(values)
    return values


# --------------------------------------------------------------------------------------
# Step 2: TLS
# --------------------------------------------------------------------------------------


def tls_dir_for(values: "dict[str, str]") -> Path:
    configured = Path(values.get("TLS_DIR") or DEFAULTS["TLS_DIR"])
    return configured if configured.is_absolute() else (ROOT / configured)


def existing_certificate_is_usable(tls_dir: Path) -> bool:
    fullchain = tls_dir / "fullchain.pem"
    key = tls_dir / "privkey.pem"
    return fullchain.is_file() and key.is_file() and pem_kind(fullchain) == "certificate"


def describe_certificate(tls_dir: Path) -> None:
    """Print who issued it, what it covers, and when it expires."""
    blocks = certificate_blocks(tls_dir / "fullchain.pem")
    if not blocks:
        return
    leaf = blocks[0]
    subject, issuer = cert_identity(leaf)
    end, days = cert_expiry(leaf)
    names = cert_san_names(leaf)

    say()
    info("Certificate in use:")
    bullet(f"issued for : {', '.join(names) if names else subject or 'unknown'}")
    bullet(f"issued by  : {issuer or 'unknown (openssl unavailable)'}")
    bullet(f"chain      : {len(blocks)} certificate(s) in fullchain.pem")
    if end:
        bullet(f"expires    : {end} ({days} days)")
        if 0 <= days < 30:
            warn(
                "This certificate expires in under 30 days. The web container turns "
                "unhealthy at that point, by design - replace it and restart web."
            )
        elif days < 0:
            die("This certificate has already expired.")


def assemble_from_supplied(tls_dir: Path, values: "dict[str, str]") -> None:
    """Guide the user through the files their CA issued, then verify and install them."""
    info(
        "You will be asked for three things. The extension does not matter - the script\n"
        "reads each file's contents to work out what it is.\n"
        "\n"
        "  the certificate   the file whose subject is your hostname\n"
        "  the intermediate  the CA's file that issued it (often named like gd_bundle)\n"
        "  the private key   the key that was generated with the CSR\n"
        "\n"
        "A .csr or .pem containing only a request is not needed and is rejected below."
    )
    say()

    for _attempt in range(5):
        raw = ask("Path to your certificate file (or 'self' for a test certificate)", default="")
        if not raw or raw.lower() == "self":
            generate_self_signed(tls_dir, values)
            return
        path = Path(raw).expanduser()
        if not path.is_file():
            warn("No such file.")
            continue
        kind = pem_kind(path)
        if kind == "certificate":
            leaf_path = path
            break
        warn(f"That file is a {kind}, not a certificate.")
    else:
        die("No certificate file was provided.", "Re-run setup.py when you have the file.")

    intermediate_paths: "list[Path]" = []
    for _attempt in range(5):
        raw = ask(
            "Path to the intermediate certificate from your CA (blank to skip)", default=""
        )
        if not raw:
            warn(
                "Without the intermediate, Chrome on a desktop may work while older "
                "Android and command-line clients fail. It is the most common TLS mistake."
            )
            if confirm("Continue without it?", default=False):
                intermediate_paths = []
                break
            continue
        path = Path(raw).expanduser()
        if not path.is_file():
            warn("No such file.")
            continue
        if pem_kind(path) != "certificate":
            warn(f"That file is a {pem_kind(path)}, not a certificate.")
            continue
        intermediate_paths = [path]
        break

    for _attempt in range(5):
        raw = ask("Path to your private key file", default="")
        path = Path(raw).expanduser()
        if not path.is_file():
            warn("No such file.")
            continue
        if pem_kind(path) != "private-key":
            warn(f"That file is a {pem_kind(path)}, not a private key.")
            continue
        key_path = path
        break
    else:
        die("No private key file was provided.", "Re-run setup.py when you have the file.")

    leaf_blocks = certificate_blocks(leaf_path)
    if not leaf_blocks:
        die("The certificate file contains no CERTIFICATE block.")
    leaf = leaf_blocks[0]

    # Intermediates: keep the ones that are not self-signed roots.
    chain_blocks: "list[str]" = []
    skipped_roots: "list[str]" = []
    for path in intermediate_paths:
        for block in certificate_blocks(path):
            subject, issuer = cert_identity(block)
            if subject and subject == issuer:
                skipped_roots.append(subject)
                continue
            chain_blocks.append(block)

    for root in skipped_roots:
        info(
            f"Skipping {root}: it is a self-signed root certificate. Browsers already have "
            "it, and including it only adds bytes to every handshake."
        )

    fullchain_text = leaf.rstrip() + "\n" + "".join(
        block.rstrip() + "\n" for block in chain_blocks
    )

    # --- verification ---
    say()
    info("Verifying before anything is installed:")

    if openssl_available():
        leaf_fp = public_key_fingerprint(leaf_path, "certificate")
        key_fp = public_key_fingerprint(key_path, "private-key")
        if leaf_fp and key_fp:
            if leaf_fp == key_fp:
                bullet("key matches the certificate")
            else:
                die(
                    "The private key does not match the certificate.",
                    "nginx would refuse to start with 'key values mismatch'. The certificate "
                    "was probably issued from a different CSR. Ask the CA or its issuer to "
                    "confirm which key belongs with it.",
                )
        else:
            warn("Could not compare the key with the certificate (openssl error).")

        subject, issuer = cert_identity(leaf)
        bullet(f"leaf subject: {subject or 'unknown'}")
        bullet(f"leaf issuer : {issuer or 'unknown'}")

        names = cert_san_names(leaf)
        if names:
            bullet(f"covers      : {', '.join(names)}")
            host = (values.get("TURNSTILE_HOSTNAMES") or "").split(",")[0].strip()
            if host and not any(self_matches(name, host) for name in names):
                warn(
                    f"The certificate does not cover '{host}', the hostname configured for "
                    "the human check. Visitors will get a name-mismatch warning."
                )

        if chain_blocks:
            # Continuity, not trust: each certificate's issuer must be the next one's
            # subject. That is what catches a missing or misordered intermediate, which
            # is the failure browsers report as "unable to get local issuer certificate".
            def normalise(dn: str) -> str:
                return ",".join(part.strip() for part in dn.split(","))

            expected = normalise(issuer)
            continuous = True
            for block in chain_blocks:
                block_subject, block_issuer = cert_identity(block)
                if normalise(block_subject) != expected:
                    continuous = False
                    break
                expected = normalise(block_issuer)
            if continuous:
                bullet("chain is continuous (leaf -> intermediate)")
            else:
                warn(
                    "The chain does not line up: the intermediate supplied did not issue "
                    "this certificate, or the order is wrong. Browsers may report "
                    "'unable to get local issuer certificate'."
                )

        end, days = cert_expiry(leaf)
        if end:
            bullet(f"expires     : {end} ({days} days)")
            if 0 <= days < 30:
                warn("This certificate expires in under 30 days.")
    else:
        warn("openssl is unavailable, so the chain and key were not verified.")

    write_tls_files(fullchain_text, key_path, tls_dir)


def self_matches(name: str, host: str) -> bool:
    """Does a certificate name cover a hostname? Handles a single leading wildcard."""
    name = name.lower()
    host = host.lower()
    if name == host:
        return True
    if name.startswith("*.") and host.endswith(name[1:]):
        return host.count(".") == name.count(".")
    return False


def generate_self_signed(tls_dir: Path, values: "dict[str, str]") -> None:
    info(
        "A self-signed certificate encrypts traffic but is not trusted by browsers, so\n"
        "every visitor gets a warning page. It exists to get a test deployment running\n"
        "and to let you exercise the containers before the real certificate arrives."
    )
    host = ask(
        "Hostname to put on the test certificate",
        default=(values.get("TURNSTILE_HOSTNAMES") or "").split(",")[0].strip() or "localhost",
    )

    if OPTIONS.dry_run:
        info(f"[dry-run] would generate a self-signed certificate for {host}")
        return

    tls_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(tls_dir, 0o700)
    code, out = openssl(
        "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365",
        "-keyout", str(tls_dir / "privkey.pem"),
        "-out", str(tls_dir / "fullchain.pem"),
        "-subj", f"/CN={host}",
        "-addext", f"subjectAltName=DNS:{host}",
    )
    if code != 0:
        die("Could not generate the test certificate.", out)
    os.chmod(tls_dir / "privkey.pem", 0o600)
    os.chmod(tls_dir / "fullchain.pem", 0o644)
    info(f"Generated a self-signed certificate for {host}, valid 365 days.")
    warn("Replace it with a real certificate before delegates use the site.")


def step_tls(values: "dict[str, str]") -> None:
    headline(2, "TLS certificate")

    tls_dir = tls_dir_for(values)
    info(
        "nginx terminates HTTPS itself, and it will not start without exactly two files:\n"
        f"\n  {tls_dir / 'fullchain.pem'}   your certificate, then its intermediate(s)\n"
        f"  {tls_dir / 'privkey.pem'}     the matching private key\n"
        "\n"
        "They are mounted read-only into the web container. They are not part of the\n"
        "image and must never be committed: a leaked private key has to be reissued."
    )

    if existing_certificate_is_usable(tls_dir):
        say()
        info(f"Both files already exist in {tls_dir}.")
        describe_certificate(tls_dir)
        if confirm("Keep this certificate and continue?", default=True):
            return
    say()
    if not interactive():
        warn(
            "No usable certificate was found and this run is unattended, so a self-signed "
            "one is generated. Replace it before delegates use the site."
        )
        generate_self_signed(tls_dir, values)
        return

    if confirm("Do you have a certificate file from your CA (as opposed to a test install)?",
               default=True):
        assemble_from_supplied(tls_dir, values)
    else:
        generate_self_signed(tls_dir, values)

    if not OPTIONS.dry_run and existing_certificate_is_usable(tls_dir):
        describe_certificate(tls_dir)


# --------------------------------------------------------------------------------------
# Step 3: containers
# --------------------------------------------------------------------------------------


def container_health(service: str) -> str:
    """'starting' | 'healthy' | 'unhealthy' | 'absent' for one compose service."""
    result = docker_compose("ps", "-q", service)
    container_id = (result.stdout or "").strip()
    if not container_id:
        return "absent"
    inspect = run(
        ["docker", "inspect", "--format", "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}", container_id]
    )
    return (inspect.stdout or "").strip() or "absent"


def wait_for_health(service: str, timeout: int = HEALTH_TIMEOUT_SECONDS) -> bool:
    say()
    info(f"Waiting for {service} to report healthy (up to {timeout}s)...")
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        state = container_health(service)
        if state != last:
            info(f"  {service}: {state}")
            last = state
        if state == "healthy":
            return True
        if state in ("unhealthy", "exited", "dead"):
            return False
        time.sleep(2)
    return False


def step_containers(values: "dict[str, str]") -> None:
    headline(3, "Building and starting the containers")

    info(
        "Three containers are created:\n"
        "\n"
        "  db    PostgreSQL 18.6, holding the conference data (not reachable from outside)\n"
        "  api   FastAPI, the application logic (not reachable from outside)\n"
        "  web   nginx: serves the built frontend, terminates TLS, proxies /api to the api\n"
        "\n"
        "The first build compiles both images and takes a few minutes. Later runs reuse\n"
        "the cached layers, so they take seconds."
    )

    port = int(values.get("WEB_PORT") or DEFAULTS["WEB_PORT"])
    if not OPTIONS.dry_run and port_in_use(port):
        warn(
            f"Something is already listening on port {port}. If it is another web server, "
            "stop it or set a different WEB_PORT before starting."
        )

    say()
    code = run_streaming(["docker", "compose", "up", "-d", "--build"])
    if code != 0:
        # `up` fails for two very different reasons - the images did not build, or they
        # built and a container refused to start - so report which one it was.
        say()
        info("Container state after the failure:")
        state = run(["docker", "compose", "ps", "-a"])
        say((state.stdout or "") + (state.stderr or ""))

        broken = [service for service in ("db", "api", "web")
                  if container_health(service) not in ("healthy", "running")]
        for service in broken:
            info(f"Recent logs from {service}:")
            logs = run(["docker", "compose", "logs", "--tail", "25", service])
            say((logs.stdout or "") + (logs.stderr or ""))

        hint = (
            "If the output above shows a build error, the usual causes are:\n"
            "  - no network access, so base images and packages cannot be pulled\n"
            "  - a syntax error in compose.yaml\n"
            "\n"
            "If the images built and a container then failed to start:\n"
            "  - 'password authentication failed' means the database volume was created\n"
            "    with a different POSTGRES_PASSWORD than the one now in .env. Either put\n"
            "    the old password back, or start over with:  docker compose down -v\n"
            "    (that deletes the conference data - only do it on a fresh install)\n"
            "  - 'address already in use' means something else owns WEB_PORT or WEB_TLS_PORT"
        )
        if broken:
            die(f"The {', '.join(broken)} container did not start.", hint)
        die("Could not start the containers.", hint)

    if OPTIONS.dry_run:
        info("[dry-run] would wait for db, api and web to report healthy")
        return

    for service in ("db", "api", "web"):
        if not wait_for_health(service):
            say()
            info(f"Recent logs from {service}:")
            logs = run(["docker", "compose", "logs", "--tail", "30", service])
            say((logs.stdout or "") + (logs.stderr or ""))
            die(
                f"The {service} container never became healthy.",
                "Read the log above. 'certificate not found' means the two files in the "
                "TLS directory are missing or misnamed; a database error means the "
                "password was changed after the data volume was first created.",
            )

    say()
    info("All three containers are healthy:")
    status = run(["docker", "compose", "ps"])
    say((status.stdout or "") + (status.stderr or ""))


# --------------------------------------------------------------------------------------
# Step 4: first-run data
# --------------------------------------------------------------------------------------


def step_bootstrap(values: "dict[str, str]") -> "str | None":
    headline(4, "Creating the schema and the first admin")

    info(
        "The database starts empty. One command creates every table, the pinned\n"
        "\"Conference Start\" timeline event, the two grading rubrics, and the first admin\n"
        "account.\n"
        "\n"
        "The admin account has no password until its access code is claimed with\n"
        "\"First-Time Register\" on the login page - so no password is ever invented here.\n"
        "Running this again never resets an existing account."
    )
    say()
    admin_name = ask("Display name for the first admin", default="Administrator")

    code, output = run_capture_streaming(
        ["docker", "compose", "run", "--rm", "api",
         "python", "-m", "crud.bootstrap", "--admin-name", admin_name]
    )
    if code != 0:
        die(
            "bootstrap failed.",
            "If it mentions DATABASE_URL, the database container is not reachable. "
            "If it mentions a duplicate key, the schema was created by an older version - "
            "see deploy/README.md.",
        )

    # "Admin access code (claim it with \"First-Time Register\")" followed by "  Name: code"
    lines = output.splitlines()
    for index, line in enumerate(lines):
        if "Admin access code" in line and index + 1 < len(lines):
            match = re.search(r":\s*(\S+)\s*$", lines[index + 1])
            if match:
                return match.group(1)
    return None


def admin_recovery_hint(values: "dict[str, str]") -> str:
    user = values.get("POSTGRES_USER") or DEFAULTS["POSTGRES_USER"]
    db = values.get("POSTGRES_DB") or DEFAULTS["POSTGRES_DB"]
    return (
        "Lost the code? Read it back:\n"
        f"  docker compose exec db psql -U {user} -d {db} "
        "-c \"select name, identifier from accounts where role='admin';\""
    )


# --------------------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------------------


def step_summary(values: "dict[str, str]", admin_code: "str | None") -> None:
    headline(5, "Done")

    host = ""
    if not OPTIONS.dry_run:
        blocks = certificate_blocks(tls_dir_for(values) / "fullchain.pem")
        if blocks:
            names = cert_san_names(blocks[0])
            host = next((name for name in names if name != "localhost"), names[0] if names else "")
    if not host:
        host = (values.get("TURNSTILE_HOSTNAMES") or "").split(",")[0].strip()

    port = values.get("WEB_TLS_PORT") or DEFAULTS["WEB_TLS_PORT"]
    suffix = "" if port == "443" else f":{port}"
    url = f"https://{host or 'YOUR-HOSTNAME'}{suffix}"

    info("The site is running.")
    say()
    info(f"  Open:      {url}")
    info("            (a self-signed certificate shows a browser warning - bypass it once)")
    say()

    if OPTIONS.dry_run:
        info("[dry-run] no admin account would be created in this mode")
    elif admin_code:
        rule("=")
        info("ADMIN ACCESS CODE - shown once, claim it now")
        rule("=")
        say(f"    {admin_code}")
        rule("=")
        info(
            "On the login page choose \"First-Time Register\", enter that code and pick a\n"
            "password. Until it is claimed, that code alone is enough to take over the\n"
            "site, so do it now rather than later."
        )
        say()
        info(admin_recovery_hint(values))
    else:
        info("The admin account already existed, so no new code was created.")
        info(admin_recovery_hint(values))

    say()
    info("Everyday commands, from this directory:")
    bullet("docker compose ps                    what is running and how healthy it is")
    bullet("docker compose logs -f web           follow nginx (the place to look first)")
    bullet("docker compose restart web           reload configuration or a new certificate")
    bullet("docker compose down                  stop everything (data is kept)")
    say()
    info("Where things live:")
    bullet(".env                                 this deployment's settings and secrets")
    bullet(f"{values.get('TLS_DIR') or DEFAULTS['TLS_DIR']}/  fullchain.pem and privkey.pem")
    bullet("volume app-data                       uploaded papers, audit logs, heartbeat")
    bullet("volume db-data                        the conference database")
    bullet("Both volumes survive `docker compose down`; only `down -v` deletes them.")
    say()
    info(
        "Back up both together - the database stores paper paths, so restoring one\n"
        "without the other gives broken downloads:"
    )
    info(
        "  docker compose exec db pg_dump -U "
        f"{values.get('POSTGRES_USER') or DEFAULTS['POSTGRES_USER']} "
        f"{values.get('POSTGRES_DB') or DEFAULTS['POSTGRES_DB']} > backup.sql"
    )
    say()
    info("Further reading: deploy/README.md (operations) and deploy/TLS.md (certificates).")
    say()
    info("Next: sign in as admin, open the Timeline tab and set the real conference start")
    info("date - the header countdown reads it.")
    say()


# --------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------


def main(argv=None) -> None:
    global OPTIONS

    parser = argparse.ArgumentParser(
        prog="setup.py",
        description="Set up and start the SCVMUN platform with Docker Compose.",
        epilog="Safe to re-run: existing settings become the defaults.",
    )
    parser.add_argument("--yes", action="store_true",
                        help="accept every default; ask nothing (for scripted installs)")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen without writing files or starting containers")
    OPTIONS = parser.parse_args(argv)

    say()
    rule("=")
    say("SCVMUN Platform - setup")
    rule("=")
    info(
        "This will configure, build and start the conference platform on this machine.\n"
        "It asks a few questions, explains each one, and checks the result as it goes.\n"
        "Nothing is installed system-wide, and re-running it is safe."
    )

    try:
        preflight()
        existing = parse_env(ENV_FILE)
        values = step_env(existing)
        step_tls(values)
        step_containers(values)
        admin_code = step_bootstrap(values)
        step_summary(values, admin_code)
    except KeyboardInterrupt:
        say()
        info("Stopped. Nothing further was changed; re-run setup.py when ready.")
        sys.exit(130)


if __name__ == "__main__":
    main()
