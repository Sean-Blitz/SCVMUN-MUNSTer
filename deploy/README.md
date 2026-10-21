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

