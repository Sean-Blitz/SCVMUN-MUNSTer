# The API image. Build context is Backend/ so the copy stays small:
#   docker build -t scvmun-api Backend/
#
# python:3.14-slim matches the interpreter the pinned requirements were resolved on
# (requirements.txt came from that venv). If the tag is unavailable on your registry,
# python:3.13-slim is the nearest safe fallback - rebuild and rerun the test suite.
FROM python:3.14-slim

# PYTHONUNBUFFERED so `docker logs` shows output as it happens; the rest keeps the image
# from writing bytecode and from caching pip downloads.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Every path the app writes to lives under /data, so one volume covers the state that must
# survive a rebuild: submitted papers, the audit logs, and the heartbeat history that the
# admin dashboard reports as uptime. STORAGE_PATH is what the dashboard measures.
ENV PAPER_UPLOAD_DIR=/data/papers \
    LOG_DIR=/data/logs \
    STORAGE_PATH=/data

# uvicorn reads this for --proxy-headers. It must name the proxy that reaches the
# container: on the host-nginx + published-port setup that is the docker bridge gateway,
# not 127.0.0.1. Override it per deployment.
ENV FORWARDED_ALLOW_IPS=172.17.0.1

WORKDIR /app

# Unprivileged, fixed uid so the host can own a bind-mounted /data correctly.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app \
    && mkdir -p /data/papers /data/logs \
    && chown -R app:app /data

# Requirements first, on their own layer: editing code does not reinstall dependencies.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app . .

USER app

VOLUME ["/data"]
EXPOSE 8000

# No curl in the slim image, so the probe is Python. It checks the database too (see
# /healthz in main.py), which is the failure a process-only check would miss.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4).status == 200 else 1)"]

# One worker on purpose: the audit logs and the heartbeat thread are per-process, and a
# conference does not need more. Add --workers only after checking core/monitor.py's
# deduplication and the log handlers again.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
