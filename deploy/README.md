# Deployment notes

## nginx: rate limits and body-size caps

Three files here:

| file | goes to | why there |
| --- | --- | --- |
| `nginx/scvmun-zones.conf` | `/etc/nginx/scvmun-zones.conf`, included from `http{}` | `limit_req_zone` is only valid in the `http` context |
| `nginx/scvmun-site.conf` | `/etc/nginx/sites-available/scvmun` (+ symlink into `sites-enabled`) | the `server{}` blocks |
| `nginx/scvmun-proxy.conf` | `/etc/nginx/snippets/scvmun-proxy.conf` | the proxy headers, defined once for three locations |

```bash
sudo cp deploy/nginx/scvmun-zones.conf /etc/nginx/scvmun-zones.conf
sudo cp deploy/nginx/scvmun-site.conf  /etc/nginx/sites-available/scvmun
sudo cp deploy/nginx/scvmun-proxy.conf /etc/nginx/snippets/scvmun-proxy.conf
sudo ln -s /etc/nginx/sites-available/scvmun /etc/nginx/sites-enabled/scvmun
# add to /etc/nginx/nginx.conf, inside http{}:
#   include /etc/nginx/scvmun-zones.conf;
sudo nginx -t && sudo systemctl reload nginx
```

Replace `<DOMAIN>`, and check that `root` in the site file matches where the frontend was
built (`npm run build` in `Frontend/`, then copy `dist/`).

### Run the API on loopback, trusting the proxy

```bash
uvicorn main:app --host 127.0.0.1 --port 8000 \
    --proxy-headers --forwarded-allow-ips=127.0.0.1
```

The two proxy flags matter: without them `request.client.host` is `127.0.0.1` for every
request, so anything that reasons about client IPs — including these limits — treats the
whole world as one client.

### What the limits are

| zone | applies to | rate | burst |
| --- | --- | --- | --- |
| `scvmun_auth` | `/api/auth/` (login, register) | 10/min per IP | 5 |
| `scvmun_upload` | `POST /api/delegate/upload-paper` | 6/min per IP | 2 |
| `scvmun_general` | everything else under `/api/` | 60/min per IP | 30 |

`burst` allows short spikes; `nodelay` serves them immediately instead of queueing. A
client that exceeds the rate gets **429** with `{"message": "..."}`, not nginx's HTML.

These are per **IP**, so a whole school behind one NAT shares a bucket — the burst values
are generous for that reason, and the per-account upload cap lives in the API instead
(`MAX_UPLOADS_PER_HOUR` in `core/controls.py`).

### Verifying without blocking anyone

Add `limit_req_dry_run on;` to the `http{}` block (or a `server{}` block) to have nginx log
what it *would* reject without rejecting it, then watch the error log:

```bash
sudo nginx -t && sudo systemctl reload nginx
tail -f /var/log/nginx/error.log | grep limiting
```

To see it actually block, send a burst and expect 429s after the burst is used up:

```bash
for i in $(seq 1 15); do
  curl -s -o /dev/null -w '%{http_code}\n' https://<DOMAIN>/api/health-check
done
```

### Body sizes

`client_max_body_size` is **1m** for everything, so a huge body cannot be posted at any
route, and **12m** only on the upload location — double the app's own 10 MB paper limit
(`PAPER_MAX_MB` in `core/storage.py`), so the app still gets to answer with its own 413
message rather than nginx's.

## Cloudflare Turnstile keys

The human check on login/register needs **both** keys, or it is off:

| where | variable | notes |
| --- | --- | --- |
| server env | `TURNSTILE_SECRET` | the widget's secret; never in the repo, and it also turns the check on |
| server env | `TURNSTILE_HOSTNAMES` | **required when the secret is set**; comma-separated frontend hostnames |
| frontend build | `VITE_TURNSTILE_SITE_KEY` | public; **baked in at build time** |

Store the secret in the ignored `Backend/crud/.env`, without ever putting it in a shell
history or a chat message:

```bash
cd Backend/crud
read -rsp 'Turnstile secret: ' s; echo
printf '\nTURNSTILE_SECRET=%s\n' "$s" >> .env
unset s
```

`TURNSTILE_HOSTNAMES` must list the frontend's hostname exactly as Siteverify reports it:

| deployment | value |
| --- | --- |
| production | `scvmun.esuhsd.org` |
| local development | `localhost,127.0.0.1` |

**Production must not include `localhost` or `127.0.0.1`.** Anyone can serve a page from
`localhost`, so a shared allow-list would let a token minted on someone else's machine pass
on the real site — which is the whole reason the flow keeps the two lists apart. An empty
list is treated as a misconfiguration and *rejects every login*, deliberately: with nothing
to compare against, accepting any hostname Cloudflare reports would make the check theatre.

The widget's own domain list (Cloudflare dashboard → Turnstile → the widget → Settings) has
to contain **both** `scvmun.esuhsd.org` and `localhost`, or the widget refuses to render on
the origin it is served from. Registering both is safe precisely because each deployment
validates its own hostname above.

The widget is rendered with `action: "auth"`, which Siteverify echoes back; the server
rejects a token minted for any other action, so the value in
`Frontend/src/views/auth/LoginRegisterView.vue` and `core/captcha.py` must stay in step.

```bash
# Frontend/.env (or .env.production) before building:
VITE_TURNSTILE_SITE_KEY=0x4AAAAAAFfdf-btRVoOqr55
cd Frontend && npm run build
```

Because Vite inlines the key, a production bundle built without it has the widget compiled
out while the API (with the secret set) still demands a token — every login would fail. Set
both, or neither.

For local development, leave both unset. To exercise the widget without a Cloudflare
account, use the published test key that always passes:
`VITE_TURNSTILE_SITE_KEY=1x00000000000000000000AA` with
`TURNSTILE_SECRET=1x0000000000000000000000000000000AA` (the test secret still calls
Cloudflare's API, so it needs network access).

Startup tells you which state you are in, in the technical log:

| log line | meaning |
| --- | --- |
| `captcha.disabled` | no `TURNSTILE_SECRET`: logins are open (development) |
| `captcha.misconfigured` | secret set but `TURNSTILE_HOSTNAMES` empty: every login is rejected |
| (neither) | the check is on |

## Running it in Docker

The image is `Backend/Dockerfile`, built from `Backend/`:

```bash
docker build -t scvmun-api Backend/
```

Everything the app writes lives under `/data` — submitted papers, audit logs, and the
heartbeat history the dashboard reports as uptime — so one volume holds all the state that
must survive a rebuild:

```bash
docker run -d --name scvmun-api \
  --env-file Backend/crud/.env \
  -e DATABASE_URL='postgresql+psycopg2://scvmun:CHANGEME@host.docker.internal:5432/scvmun' \
  -e FORWARDED_ALLOW_IPS=172.17.0.1 \
  --add-host host.docker.internal:host-gateway \
  -p 127.0.0.1:8001:8000 \
  -v /srv/scvmun/data:/data \
  --restart unless-stopped \
  scvmun-api
```

Notes that matter:

- **`-p 127.0.0.1:8001:8000`** keeps uvicorn off the public interface; nginx is the only
  thing listening publicly. Point `proxy_pass` at `127.0.0.1:8001`.
- **The driver must be in the URL**: `postgresql+psycopg2://…`, not `postgresql://`.
  SQLAlchemy resolves the bare form to the psycopg **v3** dialect, while
  `requirements.txt` installs `psycopg2-binary`, so the bare form dies at import with
  `ModuleNotFoundError: No module named 'psycopg'`. Either spell the driver out (what the
  project does) or add `psycopg[binary]` to the requirements.
- **`--add-host host.docker.internal:host-gateway`** is how the container reaches a
  Postgres on the bare metal host. Postgres needs `listen_addresses = '*'` and a
  `pg_hba.conf` line for the docker bridge, e.g.
  `host all all 172.17.0.0/16 scram-sha-256`.
- **`FORWARDED_ALLOW_IPS`** must name the proxy that reaches the container. With the
  command above that is the bridge gateway (`172.17.0.1`); leaving it at `127.0.0.1` makes
  every request look like one client and silently collapses the per-IP limits.
- **The image contains no secrets.** `Backend/crud/.env` is excluded by
  `Backend/.dockerignore` and configuration arrives through `--env-file`/`-e`.
- **One worker.** The audit log handlers and the heartbeat thread are per-process; add
  `--workers` only after revisiting `core/monitor.py`'s deduplication.
- **`/data` ownership.** The container runs as uid 10001, and storage plus audit logs are
  written `0600`, so a bind mount must be owned by that uid: `chown -R 10001:10001 /srv/scvmun/data`.

The health probe is `GET /healthz`, which runs `SELECT 1`, so `docker ps` shows unhealthy
when the API is up but the database is not. `HEALTHCHECK` is built into the image.

For local development there is a compose file at the repo root that pairs the API with a
`postgres:16` container (no Postgres install needed on the Mac):

```bash
docker compose up -d --build
docker compose exec api python -m crud.bootstrap --admin-name "You"
curl -s localhost:8001/healthz
```

## First-run bootstrap

`crud/seed.py` creates tables and nothing else. The first admin and the schools come from
`crud/bootstrap.py`, which calls the same `ensure_schema()` and then fills in rows:

```bash
# native
python -m crud.bootstrap --admin-name "Ethan Santiago" --schools ../deploy/schools.example.json

# in the container
docker compose run --rm api python -m crud.bootstrap --admin-name "Ethan" --schools /schools.json
```

- Creates every missing table, one **admin** account with no password, and one **advisor**
  account plus `School` row per entry in the `--schools` file
  (`deploy/schools.example.json` shows the shape).
- **Schools have to exist before anything else works**: `POST /admin/hashes` requires one
  and no endpoint creates it. Committees are *not* needed — minting a hash creates them —
  and the checklist and timeline are editable from the admin UI afterwards.
- Prints each access code **once**. Both the admin and every advisor claim theirs with
  "First-Time Register" on the login screen, so no password is ever invented by the script.
  A lost advisor code can be read back with
  `SELECT name, identifier FROM accounts WHERE role = 'advisor';`.
- **Idempotent**: an existing admin is left alone (never reset), an existing school is
  skipped, so re-running after adding a school only adds that school.
- Records `bootstrap.completed` in the technical log.
