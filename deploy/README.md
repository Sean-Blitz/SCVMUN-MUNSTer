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
