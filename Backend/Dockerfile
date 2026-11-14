# syntax=docker/dockerfile:1
#
# SCVMUN Platform API (FastAPI + uvicorn).
#
# Built from the Backend/ directory.
#
#     docker build -t scvmun-api Backend/
#
# Two stages. The builder turns requirements.txt into wheels; the runtime gets the
# wheels and the code, and none of the compilers.

# --- build stage -------------------------------------------------------------
FROM python:3.14-slim AS builder

# psycopg2-binary, cffi and argon2-cffi-bindings are C extensions. When a cp314
# wheel exists pip takes it; when it does not, pip compiles from source, which
# needs these headers. Keeping them out of the runtime stage is the point.
# Together, they add about 200 MB to the image, which is complete bloat.
RUN apt-get update \
 && apt-get install --no-install-recommends -y \
      build-essential \
      libpq-dev \
      libffi-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt
# This is largely a throwaway image. Later the runtime stage copies the wheels it needs.

# --- runtime stage -----------------------------------------------------------
FROM python:3.14-slim AS runtime

# The app's own configuration. Everything that must survive a rebuild is under
# /data: uploaded papers, both audit logs and the heartbeat files. Without these
# three variables the app falls back to paths inside the image, and a redeploy
# silently discards the audit trail and every submitted paper.
# App stores naive UTC time, so container's timezone is UTC.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=UTC \
    PAPER_UPLOAD_DIR=/data/papers \
    LOG_DIR=/data/logs \
    STORAGE_PATH=/data \
    FORWARDED_ALLOW_IPS=*

WORKDIR /app

# --no-index: the runtime installs only from the wheels the builder produced, so a
# missing pin fails here instead of pulling something different at run time.
COPY --from=builder /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
 && rm -rf /wheels

# A fixed uid makes the bind mount on the host predictable (chown -R 10001:10001).
# The /data directories are created here so a *named* volume inherits this
# ownership the first time it is mounted; a bind mount takes the host's.
RUN groupadd --system --gid 10001 app \
 && useradd --uid 10001 --gid app --no-create-home --home-dir /app \
            --shell /usr/sbin/nologin app \
 && mkdir -p /data/papers /data/logs \
 && chown -R app:app /data

# Copied last and owned by the unprivileged user: the app only reads its code.
# crud/.env is excluded by .dockerignore - configuration arrives as the environment.
COPY --chown=app:app . .

USER app
EXPOSE 8000

# /healthz runs SELECT 1, so this probe reports unhealthy when the API is up but
# the database is not - the failure a process-only check hides. urllib, because
# slim has no curl or wget.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"]

STOPSIGNAL SIGTERM

# --workers 1 is deliberate, not a default left in place: the audit handlers, the
# heartbeat thread and the module-level rubric state in core/controls.py are all
# per-process. More workers would duplicate heartbeats and split the audit log.
# FORWARDED_ALLOW_IPS (above) is what makes request.client.host the real caller
# behind the web container rather than the proxy's address.
CMD ["uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers", \
     "--workers", "1", \
     "--timeout-graceful-shutdown", "30"]
