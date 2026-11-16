# syntax=docker/dockerfile:1
#
# SCVMUN Platform web: the Vite build served by nginx, which also terminates TLS and
# proxies /api to the api container. This is the only image that publishes ports.
#
#     docker build -t scvmun-web Frontend/
#
# Two stages: Node only exists to produce dist/.
#
# The TLS certificate is not in this image. It is mounted at runtime from the host to
# /etc/nginx/tls/ (see deploy/TLS.md), because these images are distributed and a private
# key in a layer would be a leak.

# --- build stage -------------------------------------------------------------
FROM node:22-alpine AS build

WORKDIR /app

# Copy the manifests first so `npm ci` is cached until a dependency actually changes.
# package-lock.json is committed, so npm ci installs exactly the reviewed tree.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines these at build time, which is why they are build arguments and not
# runtime environment: changing either one requires a rebuild, not a restart.
#
# The API base is relative on purpose. The SPA then calls its own origin and nginx
# proxies /api, so this image is not tied to a hostname and can be promoted between
# environments. Baking an absolute URL (as Frontend/.env.example does for `npm run dev`)
# would make a different image per deployment.
ARG VITE_API_BASE_URL=/api
# The Turnstile site key is public and the widget is registered for both the production
# and localhost origins, so one value works everywhere. Empty disables the widget - and
# it must agree with the API's TURNSTILE_SECRET, or every login is refused.
ARG VITE_TURNSTILE_SITE_KEY=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL} \
    VITE_TURNSTILE_SITE_KEY=${VITE_TURNSTILE_SITE_KEY}

RUN npm run build


# --- runtime stage -----------------------------------------------------------
FROM nginx:1.29-alpine AS runtime

# openssl is for the HEALTHCHECK below: `openssl x509 -checkend` is what turns an expiring
# certificate into an unhealthy container. The alpine image does not ship the CLI.
RUN apk add --no-cache openssl \
 && rm -f /etc/nginx/conf.d/default.conf

# Goes into conf.d, which nginx.conf includes inside http{} - so the limit_req_zone
# directives in it are valid, and the default server there is replaced by ours.
COPY nginx/scvmun.conf /etc/nginx/conf.d/scvmun.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80 443

# Two conditions, one probe:
#
#   1. /healthz-web answers - nginx is serving. It is a plain 200 on port 80 and is never
#      redirected, so the probe does not have to follow a redirect or verify a hostname.
#   2. the mounted certificate is valid for at least 30 more days. A manual, annual
#      certificate has no renewal automation to notice its own expiry, so this is what
#      makes `docker compose ps` show the problem weeks before a browser does.
#
# 2592000 = 30 days. A dead API is the api container's healthcheck to report; marking web
# unhealthy for it would restart a working proxy.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD sh -c 'wget -q -O /dev/null http://127.0.0.1/healthz-web && openssl x509 -checkend 2592000 -noout -in /etc/nginx/tls/fullchain.pem'
