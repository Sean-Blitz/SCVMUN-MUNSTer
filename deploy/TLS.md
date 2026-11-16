# TLS: putting a certificate in front of the web container

The `web` container terminates TLS itself. There is no separate proxy container and no
Let's Encrypt automation, because the certificate is issued by a commercial CA and renewed
by hand. This page is the whole procedure: where the files go, how to assemble them, how to
check them, and what to do when they expire.

If you would rather terminate TLS somewhere else (a load balancer, Cloudflare, Caddy), see
[Terminating TLS elsewhere](#terminating-tls-elsewhere) at the end.

---

## What the container expects

Two files, these exact names, in a directory that is mounted read-only at
`/etc/nginx/tls`:

| File | Contents |
| --- | --- |
| `fullchain.pem` | **your certificate first**, then its intermediate certificate(s) |
| `privkey.pem` | the private key that matches your certificate |

The order inside `fullchain.pem` matters. If the intermediate comes first, some clients
fail with "unable to get local issuer certificate" while browsers that cache intermediates
still work — which makes it look intermittent.

By default the directory is `./tls` next to `compose.yaml`. Override it with `TLS_DIR` in
`.env` if the material lives somewhere else (for example `/srv/scvmun/tls`).

`tls/`, `*.pem`, `*.crt` and `*.key` are in `.gitignore`. **Keep it that way.** This
repository is public: a private key that reaches it must be treated as leaked and reissued.

---

## 1. Work out which file is which

A commercial CA typically delivers several files. Identify them by subject and issuer
rather than by filename — nobody names them consistently:

```bash
for f in *.pem *.crt; do
  echo "=== $f"
  openssl x509 -in "$f" -noout -subject -issuer -dates 2>/dev/null || echo "  not a certificate"
done
```

- **Your certificate (the leaf)** has your hostname as its subject, e.g.
  `subject=CN = mun.school.edu`. It is the one whose issuer is *not* itself.
- **The intermediate** has the CA's name as its subject (GoDaddy: something like
  `CN = Go Daddy Secure Certificate Authority - G2`).
- **The root** has the CA root as its subject *and* as its issuer (self-signed). It is not
  needed in `fullchain.pem` — every browser already has it.
- **A "cross" certificate** is an alternative intermediate, cross-signed by an older root,
  for very old Android devices. Optional.

A `.csr` file is not needed at runtime. It was the request that produced the certificate;
nginx never reads it.

## 2. Build the two files

```bash
mkdir -p tls

# leaf first, then the intermediate(s)
cat your-certificate.pem intermediate.pem > tls/fullchain.pem
cp your-private-key.pem tls/privkey.pem
chmod 700 tls
chmod 644 tls/fullchain.pem
chmod 600 tls/privkey.pem
```

Two details:

- **Chain the intermediate in.** Serving only the leaf works in Chrome on a desktop and
  fails on older Android, some school proxies, and every command-line client. It is the
  single most common TLS misconfiguration.
- **Do not include the root.** It adds bytes to every handshake and changes nothing.

If your CA also issued a cross certificate and you want the extra compatibility with
pre-2015 Android, append it as well: `cat leaf.pem intermediate.pem cross.pem > fullchain.pem`.
Most deployments do not need it.

## 3. Check before you start

Three checks, all of which catch a failure that would otherwise appear as a confusing
nginx startup error or a browser warning.

**The key matches the certificate.** These two fingerprints must be identical:

```bash
openssl x509 -in tls/fullchain.pem -noout -pubkey | openssl sha256
openssl pkey -in tls/privkey.pem -pubout | openssl sha256
```

If they differ, the certificate was issued from a different CSR or key, and nginx will
refuse to start with `SSL_CTX_use_PrivateKey ... key values mismatch`.

**The chain is complete.** This must print `OK`:

```bash
openssl verify -CAfile root.pem -untrusted intermediate.pem your-certificate.pem
```

**The certificate covers the hostname users type**, including any `www.` variant:

```bash
openssl x509 -in tls/fullchain.pem -noout -ext subjectAltName
```

## 4. Start it

```bash
docker compose up -d --build
docker compose ps      # web should reach "healthy"
```

> **Fresh install?** The database needs its schema before the site is useful. After `up`:
>
> ```bash
> docker compose run --rm api python crud/seed.py
> docker compose run --rm api python -m crud.bootstrap --admin-name "Your Name"
> ```
>
> `seed.py` creates the tables and the pinned "Conference Start" event; `bootstrap.py` mints
> the first admin access code and prints it **once**. Claim it with "First-Time Register" on
> the login page. If you lose it:
> `docker compose exec db psql -U scvmun -d scvmun -c "select name, identifier from accounts where role='admin';"`

Then, from outside the host:

```bash
curl -sI https://your.hostname/ | head -1                       # 200
curl -sI http://your.hostname/ | grep -i location               # 301 -> https
curl -s https://your.hostname/api/conference                    # JSON from the API
```

The `Strict-Transport-Security` header should be present with `max-age=31536000` and
**without** `includeSubDomains` — this host is a subdomain of a domain somebody else
controls, and that flag would force HTTPS on their other hosts.

## 5. Renewal

There is no automation. The certificate is annual and manual, which is why the container's
healthcheck watches it: **`docker compose ps` reports `web` as unhealthy once the
certificate has less than 30 days left.** That is your warning, well before a browser starts
showing an interstitial.

Check by hand at any time:

```bash
openssl x509 -in tls/fullchain.pem -noout -enddate
openssl x509 -checkend 2592000 -noout -in tls/fullchain.pem \
  && echo "more than 30 days left" || echo "EXPIRING within 30 days"
```

When the new certificate arrives:

```bash
# replace the two files, keeping the same names and permissions
cat new-certificate.pem new-intermediate.pem > tls/fullchain.pem
cp new-private-key.pem tls/privkey.pem
chmod 600 tls/privkey.pem

# nginx reads the certificate at startup, so a restart is what activates it
docker compose restart web
docker compose ps
```

`docker compose exec web nginx -s reload` also works and avoids a few seconds of downtime,
but `restart` is the one that cannot go wrong.

## 6. Troubleshooting

| Symptom | Cause |
| --- | --- |
| nginx exits with `cannot load certificate "/etc/nginx/tls/fullchain.pem"` | the mount is empty or the filenames differ. `TLS_DIR` must contain exactly `fullchain.pem` and `privkey.pem` |
| `key values mismatch` | the key and certificate do not belong together — check the two fingerprint commands above |
| Browser: `NET::ERR_CERT_AUTHORITY_INVALID`, `curl` works | the intermediate is missing from `fullchain.pem` |
| Browser: `NET::ERR_CERT_COMMON_NAME_INVALID` | the hostname is not covered by the certificate's SANs, or DNS points at a different machine |
| Redirect loop | something in front is already terminating TLS and forwarding as HTTP; see below |
| `web` healthy, `/` returns 502 on an API call | the `api` container is down — that is its healthcheck's job, not nginx's |
| `web` unhealthy but the site works | the certificate has under 30 days left — that is the renewal warning |

## Terminating TLS elsewhere

If you put Cloudflare, a load balancer or another proxy in front, the container's port 80
becomes the entry point and the certificate mount is only needed for direct access. Two
things must change, and the second is the one people forget:

1. Stop publishing 443, or keep it for direct access only.
2. **The rate limits break.** `limit_req_zone` in `Frontend/nginx/scvmun.conf` keys on
   `$binary_remote_addr`, which becomes the proxy's address — so the whole conference shares
   one bucket and gets 429s under load. Add the provider's real-IP directives first, e.g. for
   Cloudflare:

   ```nginx
   set_real_ip_from <cloudflare ranges>;
   real_ip_header CF-Connecting-IP;
   ```

   and for a container proxy on the compose network, `real_ip_header X-Forwarded-For;` plus
   the network's subnet in `set_real_ip_from`.

`deploy/nginx/` holds the equivalent configuration for a bare-metal nginx install, which
is useful as a reference for the same rate limits and body caps.
