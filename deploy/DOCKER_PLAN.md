# Plan: package the FastAPI backend as a Docker container (Postgres stays on the Ubuntu host)

Status: **plan only — no files created yet.** This document is the input to writing
`Backend/Dockerfile`, `Backend/.dockerignore`, and `docker-compose.yml`.

Target topology:

```
Ubuntu host
├── postgresql @ 127.0.0.1:5432        (bare metal, NOT in a container)
├── nginx      @ 0.0.0.0:80/443        (serves Frontend/dist, proxies /api)
└── docker
    └── scvmun-api                     (uvicorn, published on 127.0.0.1:8001)
        └── /data volume               (papers + audit logs + heartbeat)
```

---

## 1. What the backend actually needs at runtime

Verified by reading `Backend/` directly, not assumed.

| Requirement | Finding | Source |
| --- | --- | --- |
| Python version | **3.14.5** (CPython, Homebrew venv `.venv`, `include-system-site-packages = false`) | `Backend/.venv/pyvenv.cfg` |
| Runtime deps | 20 pinned packages, all pure-Python or wheeled C extensions: `fastapi 0.141.1`, `starlette 1.6.0`, `uvicorn 0.52.4`, `SQLAlchemy 2.1.3`, `psycopg2-binary 2.9.13`, `pydantic 2.13.4`, `argon2-cffi 25.1.0`, `python-dotenv`, `python-multipart` | `Backend/requirements.txt` |
| Dev-only deps | `pytest 9.2.0`, `httpx2 2.16.0` — explicitly kept out of the runtime image | `Backend/requirements-dev.txt` |
| System packages | **None.** No `subprocess`, no `pdftotext`, no LibreOffice, no `shutil.which` anywhere in the code | grep over `Backend/**/*.py` |
| Database | Postgres over `psycopg2`; the URL **must** spell `postgresql+psycopg2://` | `Backend/crud/db.py` |
| Writes to disk | 4 kinds of file: uploaded papers, `technical.log`, `business.log`, and `heartbeat.log` + `downtime.log` — all created mode `0600` | `core/storage.py`, `core/audit.py`, `core/monitor.py` |
| Outbound network | HTTPS POST to `challenges.cloudflare.com` for Turnstile, 5s timeout, only on login/register | `core/captcha.py` |
| Inbound | HTTP only (uvicorn). No static file mounts, no TLS — nginx terminates TLS | `main.py`, `deploy/nginx/` |
| Health probe | `GET /healthz` runs `SELECT 1` and returns **503** when the DB is unreachable | `main.py:195` |
| Migrations | **None.** Schema comes from `Base.metadata.create_all()`, which creates missing tables but never `ALTER`s an existing one | `crud/seed.py:43`, `crud/bootstrap.py` |
| Process-model constraints | Heartbeat thread + per-process file log handlers + module-level mutable state in `core/controls.py` ⇒ **must run one worker** | `core/monitor.py`, `core/audit.py`, `core/controls.py` |

### Every environment variable the app reads

| Variable | Read by | Container value | Consequence if unset |
| --- | --- | --- | --- |
| `DATABASE_URL` | `crud/db.py` | `postgresql+psycopg2://scvmun:PW@172.17.0.1:5432/scvmun` | **Process exits at import** with `SystemExit` |
| `PAPER_UPLOAD_DIR` | `core/storage.py` | `/data/papers` | Falls back to `/app/crud/pdf_uploads` — **wiped on every recreate** |
| `LOG_DIR` | `core/audit.py` | `/data/logs` | Falls back to `/app/logs` — audit history **lost on recreate** |
| `STORAGE_PATH` | `core/domain/admin/interface.py` | `/data` | Reports the container overlay fs instead of the real volume |
| `PAPER_MAX_MB` | `core/storage.py` | `10` (matches nginx `12m` cap) | Defaults to 10, consistent with nginx |
| `TURNSTILE_SECRET` | `core/captcha.py` | real secret | Check silently disabled; startup logs `captcha.disabled` |
| `TURNSTILE_HOSTNAMES` | `core/captcha.py` | `scvmun.esuhsd.org` | Secret set + empty list ⇒ **every login rejected** |
| `CORS_ALLOW_ORIGINS` | `main.py:72` | `https://scvmun.esuhsd.org` | Defaults to `localhost:5173` ⇒ browser CORS failures in prod |
| `FORWARDED_ALLOW_IPS` | uvicorn (env) | `172.17.0.1` | `request.client.host` is the bridge IP ⇒ per-IP logic sees one client |

Two of these are load-bearing beyond convenience: **`PAPER_UPLOAD_DIR` and `LOG_DIR` are
the difference between durable state and state that disappears on `docker compose up
--force-recreate`.**

### Things that must NOT enter the image

`.venv/`, `__pycache__/`, `crud/.env` (secrets), `crud/pdf_uploads/*`, `logs/*`,
`tests/`, `requirements-dev.txt`, `example.py` (a stray second `FastAPI()` app),
`.DS_Store`. This is the job of `Backend/.dockerignore`; without it the local `.venv`
(several hundred MB, macOS binaries) and the developer's `.env` are baked in.

---

## 2. Decisions to make before writing files

| # | Decision | Recommendation | Why |
| --- | --- | --- | --- |
| D1 | Base image | `python:3.14-slim`, pinned **by digest** | Matches the dev interpreter exactly. See R1 for the wheel risk. |
| D2 | Single vs multi-stage | Multi-stage: `builder` compiles wheels, `runtime` gets only wheels + code | Keeps `gcc`, `libpq-dev`, `libffi-dev` out of the shipped image; costs nothing. |
| D3 | How the container reaches host Postgres | Docker **bridge** + `--add-host host.docker.internal:host-gateway` | Isolated, standard, matches the existing `deploy/README.md`. `--network host` is the alternative (see R3) but abandons isolation and port mapping. |
| D4 | Public port | Publish `127.0.0.1:8001` → container `8000` | Only nginx is public. **But** `deploy/nginx/scvmun-site.conf` still proxies to `127.0.0.1:8000` — pick one and fix the other. |
| D5 | Orchestration | Root `docker-compose.yml` with a single `api` service | `deploy/README.md` already advertises one; it does not exist. Compose gives restart policy, healthcheck dependency, env-file, and `run --rm` for bootstrap. |
| D6 | Secrets | `--env-file ~/.scvmun/api.env` (mode 0600), never `-e DATABASE_URL=...` on the command line | The README's `-e` example puts the DB password in shell history and `ps`. |
| D7 | UID | Non-root `10001:10001`, matching the README | `/data` must be `chown -R 10001:10001` on the host or the app cannot write. |
| D8 | `PAPER_UPLOAD_DIR`/`LOG_DIR` | Explicitly `/data/papers`, `/data/logs` | Not defaults. See §1. |

---

## 3. Image design (what the Dockerfile will contain)

**Stage 1 — builder**
- `python:3.14-slim` base.
- `apt-get install --no-install-recommends gcc libpq-dev libffi-dev` (only if R1 confirms a
  wheel is missing; if all wheels exist, this stage can be skipped entirely).
- `pip wheel -r requirements.txt -w /wheels` so the runtime stage never compiles.

**Stage 2 — runtime**
- Fresh `python:3.14-slim`, pinned by digest.
- `pip install --no-cache-dir --no-index --find-links /wheels -r requirements.txt`.
- `ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 TZ=UTC` — unbuffered so `docker logs`
  is real-time, no `.pyc` so the root fs can later be made read-only, UTC so audit stamps
  (already `time.gmtime`) and DB naive-UTC agree.
- Copy `Backend/` → `/app` as `--chown=10001:10001`, set `WORKDIR /app` (the app must start
  from `Backend/` for `API.*`, `core.*`, `crud.*`, `schemas.*` to import).
- Create `/data/papers` and `/data/logs` owned by `10001` — **as a fallback only**, the
  volume is the real store.
- `USER 10001:10001`.
- `EXPOSE 8000` (documentation only — the actual bind is `0.0.0.0:8000` inside the
  container, which is required for the port mapping to work; `127.0.0.1` there would be
  unreachable from the bridge).
- `HEALTHCHECK` → `GET /healthz` every 30s, timeout 5s, 3 retries, 20s start period,
  probe written with `python -c` + `urllib` because `slim` has no `curl`.
- `STOPSIGNAL SIGTERM` and a uvicorn `--timeout-graceful-shutdown 30` so the heartbeat
  thread's `stop()` and in-flight uploads finish.
- `CMD`: `uvicorn main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=${FORWARDED_ALLOW_IPS} --workers 1`.

**Hard constraint: `--workers 1`.** The audit log handlers and the heartbeat thread are
per-process, `core/controls.py` keeps rubric data in module-level lists, and
`core/monitor.py`'s dedup assumes one writer. Scaling out is a code change, not a flag.

---

## 4. Ubuntu host preparation (one-time)

1. **Docker Engine** (not Desktop) from Docker's apt repo; add the deploy user to `docker`
   or use `sudo`.
2. **Postgres role + database** for the app — a dedicated `scvmun` role with a strong
   password and its own database, not the `postgres` superuser. Current dev uses
   `postgres:scvmun-dev@localhost:5432/scvmun` — that password must not be reused.
3. **Make Postgres reachable from the bridge**:
   - `listen_addresses = 'localhost'` is **not enough** — add the docker bridge address, or
     `'*'` if the host is not otherwise exposed.
   - `pg_hba.conf`: one line for the bridge, e.g. `host all all 172.17.0.0/16 scram-sha-256`.
     Prefer the bridge subnet over `0.0.0.0/0`.
   - Reload with `SELECT pg_reload_conf();` and verify from inside a container, not from the
     host — the host-side `psql` proves nothing about bridge reachability.
4. **Firewall**: `5432` must stay closed to the internet. Allow only the docker bridge
   subnet; do **not** publish 5432. Since the API is published to `127.0.0.1:8001`, the
   DOCKER-USER chain is not a concern, but confirm `ufw` does not expose 5432.
5. **Data directory** `/srv/scvmun/data` with `chown -R 10001:10001`, on a filesystem with
   room for papers (10 MB × delegates × re-uploads). A bind mount is preferred over a named
   volume so `rsync`/backups are ordinary file operations.
6. **Secrets file** `/home/<deploy>/.scvmun/api.env`, `chmod 600`, containing the eight
   variables from §1. Not in the repo, not in the image.
7. **nginx**: point `proxy_pass` at the published port (`127.0.0.1:8001` per D4) and keep
   `--proxy-headers` + `FORWARDED_ALLOW_IPS` in step, or every client looks like one IP and
   the per-IP rate limits in `deploy/nginx/scvmun-zones.conf` collapse.

---

## 5. Data layout and consistency

One volume, three subdirectories, because three subsystems write independently:

| Path | Written by | Backup criticality |
| --- | --- | --- |
| `/data/papers/` | `core/storage.py` — files named `delegate-<id>-<hex>.pdf` | **Must match the DB.** `position_papers` stores only relative paths, so restoring one without the other yields broken downloads. |
| `/data/logs/technical.log`, `business.log` | `core/audit.py`, mode 0600 | Audit trail; append-only, never rotated by the app |
| `/data/logs/heartbeat.log`, `downtime.log` | `core/monitor.py` | Backs the admin dashboard's uptime report |

Backup procedure must be ordered: `pg_dump` **and** a tarball of `/data`, taken in the same
window, and labelled with the same timestamp. Restoring only the database leaves every
paper link dangling.

Log rotation: **the app never rotates.** `technical.log` grows with every login. Either
`logrotate` the bind mount from the host (`copytruncate`, since the app holds the handle
open) or accept unbounded growth and monitor the volume. Decide before the conference, not
during it.

---

## 6. First run and schema

1. `docker compose build`
2. **Schema + seed, one-shot**, before the service is allowed to take traffic:
   - `docker compose run --rm api python crud/seed.py` — creates tables and inserts the
     pinned "Conference Start" row.
   - `docker compose run --rm api python -m crud.bootstrap --admin-name "..." --schools /schools.json`
     — first admin + schools. This prints each access code **once** to stdout, so run it
     attached and capture the output; `docker compose logs` afterwards is not a substitute
     for a lost code (recover advisor identifiers with SQL, admins are not resettable).
   - Do **not** wire bootstrap into the container entrypoint: it is idempotent, but a
     restart must never mint credentials.
3. **Pre-flight schema audit against the host DB.** `create_all()` will not add a column to
   an existing table. If the host database predates commit `ca9989b`, `timeline_events` has
   no `pinned` column and `GET /conference` returns 500 — the exact failure mode that makes
   the header timer disappear. Check `timeline_events.pinned` exists and that a row with
   `pinned = true` is present before declaring the deploy done.
4. `docker compose up -d`, then verify §7.

Because there is no migration tool, **every future schema change needs a manual, documented
statement on the host database.** Adopting Alembic is out of scope here but should be
scheduled before the second deploy, not after a broken one.

---

## 7. Verification checklist (acceptance criteria)

| Check | Expected |
| --- | --- |
| `docker ps` | container `healthy`, not restarting |
| `curl 127.0.0.1:8001/healthz` | `{"status":"ok"}` — proves the bridge reaches Postgres |
| Stop Postgres briefly (`systemctl stop postgresql`) | `/healthz` → 503, container reports `unhealthy`, API stays up |
| `curl 127.0.0.1:8001/api/conference` | non-null `starts_at` — proves the seed ran |
| Log in through nginx | succeeds, and `technical.log` on the **host** at `/srv/scvmun/data/logs/` gains a line |
| Upload a paper, then `docker compose up -d --force-recreate` | paper still downloadable afterwards |
| `docker exec` as `10001` | cannot write outside `/data`; `id` is not root |
| Restart the container twice in 5 minutes | `downtime.log` records one `service restart`, not an outage storm |
| Admin dashboard | storage reports the `/data` volume, **not** a ~60 GB overlay |
| `docker history` / image scan | no `.env`, no `TURNSTILE_SECRET` string |
| From a browser on the public origin | CORS preflight succeeds (`CORS_ALLOW_ORIGINS` set) |

---

## 8. Risks and gotchas

| # | Risk | Severity | Mitigation |
| --- | --- | --- | --- |
| R1 | **No cp314 wheels** for `psycopg2-binary`, `cffi`, `argon2-cffi-bindings`; pip falls back to a source build that fails without `gcc`/`libpq-dev` | High | Verify **before** committing to 3.14: attempt a wheel-only install in a throwaway `python:3.14-slim`. Fallbacks, in order: (a) multi-stage builder with `gcc libpq-dev libffi-dev`; (b) `python:3.13-slim` after running the test suite; (c) swap `psycopg2-binary` → `psycopg[binary]` (requires the `postgresql+psycopg://` URL). |
| R2 | **Audit logs and papers default to inside the image** and vanish on recreate | High | Set `PAPER_UPLOAD_DIR` and `LOG_DIR` explicitly; add the upload→recreate check to §7. |
| R3 | **Port monitor is meaningless in a bridge container.** `core/domain/admin/interface.py` probes `127.0.0.1:22/80/443`, which inside the container is the container's own loopback — SSH/HTTP/HTTPS always look down on the admin dashboard | Medium | Either accept a permanently-red port panel, or make the probe addresses configurable (small code change, out of scope here), or run `--network host` and lose isolation/port mapping. Decide explicitly; do not let it be discovered by an admin on conference day. |
| R4 | `STORAGE_PATH` default `/` reports the container overlay | Medium | Set `STORAGE_PATH=/data`. |
| R5 | nginx `proxy_pass` says **8000**, README says publish **8001** | Medium | Reconcile to one port in the same change that adds the Dockerfile. |
| R6 | `CORS_ALLOW_ORIGINS` left at its `localhost:5173` default | High (silent) | Set it in the env file; verify from the real origin (§7). |
| R7 | `DATABASE_URL` written as bare `postgresql://` | High | SQLAlchemy resolves that to psycopg **v3**, which is not installed → `ModuleNotFoundError` at startup. Spell the driver. |
| R8 | `FORWARDED_ALLOW_IPS` left at `127.0.0.1` | Medium | Per-IP limiting silently becomes global. Set it to the bridge gateway. |
| R9 | Secrets in the image via `.venv`/`.env` copy | High | `.dockerignore` first, then build; grep the image. |
| R10 | No migrations + `create_all` | Medium | Pre-flight audit (§6.3); manual SQL for schema changes; schedule Alembic. |
| R11 | `crud/seed.py`/`bootstrap.py` use `load_dotenv()`, which reads `.env` from the CWD | Low | Harmless in the container (no `.env` there) — but it means a stray `.env` in the image would silently override the env file. |
| R12 | Heartbeat marks every deploy as downtime if the gap exceeds 60s | Low | Accept, or `docker restart` rather than recreate, and expect one `service restart` line per deploy. |
| R13 | Turnstile needs outbound HTTPS; a locked-down host firewall makes every login 503 | Medium | Verify outbound egress during the smoke test, with the real secret. |
| R14 | `Backend/example.py` is a second FastAPI app | Low | Exclude from the image; do not let a future `uvicorn example:app` confuse anyone. |
| R15 | Tests are a 2-line stub and `Backend/tests/` is untracked | Low | Do not gate the deploy on CI yet; gate it on §7 instead. |

---

## 9. Work order

1. Resolve **D1/R1** first — it determines whether the build has a compiler stage.
2. Reconcile the port (**D4/R5**) and write the env file on the host.
3. Add `Backend/.dockerignore`, then `Backend/Dockerfile` (per §3).
4. Add root `docker-compose.yml`: `api` service only, `extra_hosts` for
   `host.docker.internal:host-gateway`, `env_file`, `127.0.0.1:8001:8000`,
   `/srv/scvmun/data:/data`, `restart: unless-stopped`, healthcheck from the image.
   Optional `postgres` service behind a `dev` profile for macOS development only — it must
   not be part of the Ubuntu deployment.
5. Update `deploy/README.md` so its Docker section describes what actually exists (it
   currently documents `Backend/Dockerfile`, `Backend/.dockerignore` and a root compose file
   that are all missing), and replace the `-e DATABASE_URL=` example with the env file.
6. Host prep (§4), first run (§6), verify (§7).
7. Only then: hand the URL to the coworker.

## 10. Open questions

1. Is the API the **only** thing going into Docker, or should nginx and `Frontend/dist` follow later?
2. What Postgres version is on the Ubuntu host, and does the app's schema already exist there
   (i.e. is this a migration of a live database or a fresh one)?
3. Is the host reachable from the internet directly, or behind the Cloudflare proxy the
   Turnstile setup implies?
4. How much downtime is acceptable per deploy? (Recreate + one `service restart` line in
   `downtime.log` is the floor.)
5. Should `/data` be a bind mount on the data disk (recommended for backups) or a named volume?
6. Who owns backups during the conference week, and has a restore been rehearsed?
