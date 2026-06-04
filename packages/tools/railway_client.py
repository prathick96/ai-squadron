"""
packages/tools/railway_client.py
Railway REST + GraphQL deployment client for AI Squadron SaaS ventures.

Deployment flow
--------------
1. Resolve project + environment (3-tier: auto-injected IDs → project lookup → me query)
2. Get or create a Railway service for this venture
3. Get or create a Railway domain for the service (so we have the URL before deploy)
4. Pack dist/ + Dockerfile + nginx.conf into a .tar.gz
5. POST tarball to Railway upload endpoint → uploadId
6. deploymentCreate(serviceId, environmentId, sourceUploadId)
7. Poll until SUCCESS / FAILED / CRASHED
8. Return the service domain URL

WHY Dockerfile instead of Nixpacks:
  • Generated package.json has no `start` script — Nixpacks can't run the app after building.
    This was the root cause of "services created, nothing deployed."
  • Docker + nginx is 30-60s vs 2-3 min for a full Nixpacks rebuild from source.
  • Predictable: always serves the pre-built dist/ on port 8080, SPA routing included.

WHY service domain instead of deployment.url:
  • deployment.url is null for Nixpacks/Docker deployments on Railway (it's set only for
    static-file deployments, not container workloads).
  • The real URL lives on serviceInstance.domains — we query/create it before deploying.
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import tarfile as tarfile_mod
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_GRAPHQL_URL   = "https://backboard.railway.app/graphql/v2"
_POLL_INTERVAL = 8     # seconds between status checks
_DEPLOY_TIMEOUT = 600  # 10 minutes — Docker build + container start

_EXCLUDE_DIRS = {"node_modules", ".git", ".cache", "__pycache__", ".vite"}

# ─── Embedded Dockerfile for static SPA serving ───────────────────────────────
# Railway detects the Dockerfile and uses Docker instead of Nixpacks.
# nginx:alpine is ~20MB and starts in <1s.  Port 8080 matches EXPOSE below.
_DOCKERFILE = """\
FROM nginx:1.27-alpine

# Copy pre-built assets
COPY dist/ /usr/share/nginx/html/

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Railway routes to whatever port $PORT specifies (default 8080)
ENV PORT=8080
EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
"""

# SPA nginx config — serves index.html for all unknown routes (client-side routing).
# Includes hardened security headers and rate limiting for all deployed products.
_NGINX_CONF = """\
# Rate limiting: 30 req/s per IP, burst of 60 — protects against scraping and brute force
limit_req_zone $binary_remote_addr zone=per_ip:10m rate=30r/s;

server {
    listen 8080;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Hide nginx version from attackers
    server_tokens off;

    # ── Security headers ──────────────────────────────────────────────────
    # Prevent clickjacking
    add_header X-Frame-Options "SAMEORIGIN" always;
    # Prevent MIME-type sniffing
    add_header X-Content-Type-Options "nosniff" always;
    # Block reflected XSS (legacy browsers)
    add_header X-XSS-Protection "1; mode=block" always;
    # Limit referrer information leakage
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    # Restrict browser features
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(self)" always;
    # Content Security Policy — allows Supabase, PostHog, Paddle; blocks inline eval
    add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.paddle.com https://us.i.posthog.com; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src 'self' https://*.supabase.co https://us.i.posthog.com https://api.razorpay.com https://lumberjack.razorpay.com; frame-src https://api.razorpay.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self';" always;
    # HSTS — tell browsers to always use HTTPS (1 year)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Apply rate limiting to all requests
    limit_req zone=per_ip burst=60 nodelay;

    # React / Vue / Svelte SPA: unknown paths → index.html
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache hashed assets forever (Vite fingerprints filenames)
    # .map files are excluded from production — source maps expose source code
    location ~* \\.(js|css|woff2|woff|ttf|eot|ico|png|jpg|jpeg|gif|svg|webp)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        access_log off;
    }

    # Block source map files in production (security: don't expose minified source)
    location ~* \\.map$ {
        return 404;
        access_log off;
    }

    # Block access to hidden files (.env, .git, etc.)
    location ~ /\\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    # Health check endpoint for Railway (no rate limit, no headers logged)
    location /healthz {
        limit_req off;
        return 200 "ok";
        add_header Content-Type text/plain;
        access_log off;
    }

    gzip on;
    gzip_types text/plain text/css application/javascript application/json
               image/svg+xml application/font-woff2;
    gzip_min_length 1024;
    # Don't gzip already-compressed formats
    gzip_disable "msie6";
}
"""


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _get_railway_token() -> str:
    return os.getenv("RAILWAY_TOKEN", "") or os.getenv("RAILWAY_API_TOKEN", "")


def railway_available() -> bool:
    token = _get_railway_token()
    return bool(token and len(token) > 10 and not token.startswith("your_"))


async def deploy_to_railway(venture_id: str, build_dir: Path) -> str:
    """
    Deploy the dist/ folder to Railway via Docker + nginx.
    Returns the live https://*.up.railway.app URL.
    Raises RuntimeError on failure.
    """
    token        = _get_railway_token()
    service_name = f"aisq-{venture_id[:24].replace('_', '-')}"

    forced_pid = os.getenv("RAILWAY_PROJECT_ID", "")
    forced_env = os.getenv("RAILWAY_ENVIRONMENT_ID", "")

    async with httpx.AsyncClient(timeout=60.0) as client:
        # ── 1. Resolve project + environment ────────────────────────────────
        if forced_pid and forced_env:
            project_id, env_id = forced_pid, forced_env
            log.info("[RAILWAY] Using injected project=%s env=%s",
                     project_id[:8], env_id[:8])
        elif forced_pid:
            data = await _gql(client, token, _Q_PROJECT_BY_ID, {"id": forced_pid})
            envs = _unwrap_edges(data["project"]["environments"])
            project_id, env_id = forced_pid, _pick_prod_env(envs)
            log.info("[RAILWAY] project=%s env=%s (env resolved)", project_id[:8], env_id[:8])
        else:
            log.info("[RAILWAY] No RAILWAY_PROJECT_ID — running me-query (User Token)")
            project_id, env_id = await _get_or_create_project(client, token, "ai-squadron")
            log.info("[RAILWAY] project=%s env=%s", project_id[:8], env_id[:8])

        # ── 2. Service ───────────────────────────────────────────────────────
        service_id = await _get_or_create_service(
            client, token, project_id, service_name
        )
        log.info("[RAILWAY] service=%s (%s)", service_id[:8], service_name)

        # ── 3. Domain — get or create BEFORE deploying so we have the URL ───
        domain_url = await _ensure_service_domain(client, token, service_id, env_id)
        log.info("[RAILWAY] domain=%s", domain_url)

        # ── 4. Tarball — dist/ + Dockerfile + nginx.conf ────────────────────
        tarball = _make_tarball(build_dir)
        log.info("[RAILWAY] Tarball %.1f KB", len(tarball) / 1024)

        # ── 5. Upload ────────────────────────────────────────────────────────
        upload_id = await _upload_tarball(client, token, tarball)
        log.info("[RAILWAY] uploadId=%s", upload_id[:16] if upload_id else "?")

        # ── 6. Create deployment ─────────────────────────────────────────────
        deploy_id = await _create_deployment(client, token, service_id, env_id, upload_id)
        log.info("[RAILWAY] deploymentId=%s — polling…", deploy_id[:16])

        # ── 7. Poll until SUCCESS ────────────────────────────────────────────
        await _poll_deployment(client, token, deploy_id)

        return domain_url or f"https://{service_name}.up.railway.app"


# ---------------------------------------------------------------------------
# GraphQL helper
# ---------------------------------------------------------------------------

async def _gql(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    variables: dict,
) -> dict:
    resp = await client.post(
        _GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        timeout=30.0,
    )
    try:
        body_text = resp.text
    except Exception:
        body_text = "<unreadable>"

    if not resp.is_success:
        log.error("[RAILWAY] HTTP %d | body=%s", resp.status_code, body_text[:500])
        raise RuntimeError(f"Railway HTTP {resp.status_code}: {body_text[:300]}")

    body = resp.json()
    if errors := body.get("errors"):
        msg = errors[0].get("message", str(errors))
        log.error("[RAILWAY] GraphQL error: %s", msg)
        raise RuntimeError(f"Railway GraphQL error: {msg}")

    return body["data"]


# ---------------------------------------------------------------------------
# Project management
# ---------------------------------------------------------------------------

_Q_MY_PROJECTS = """
query MyProjects {
  me {
    id
    projects {
      edges {
        node {
          id
          name
          environments { edges { node { id name } } }
        }
      }
    }
  }
}
"""

_M_CREATE_PROJECT = """
mutation CreateProject($name: String!) {
  projectCreate(input: { name: $name }) {
    id
    environments { edges { node { id name } } }
  }
}
"""

_Q_PROJECT_BY_ID = """
query ProjectById($id: String!) {
  project(id: $id) {
    id
    environments { edges { node { id name } } }
  }
}
"""


async def _get_or_create_project(
    client: httpx.AsyncClient,
    token: str,
    name: str,
) -> tuple[str, str]:
    try:
        data = await _gql(client, token, _Q_MY_PROJECTS, {})
    except Exception as exc:
        raise RuntimeError(
            "Railway 'me' query failed — set RAILWAY_PROJECT_ID env var "
            "OR use a User Account Token (Account Settings → Tokens).\n"
            f"Detail: {exc}"
        ) from exc

    projects = _unwrap_edges(data["me"]["projects"])
    for p in projects:
        if p["name"] == name:
            envs = _unwrap_edges(p["environments"])
            return p["id"], _pick_prod_env(envs)

    data    = await _gql(client, token, _M_CREATE_PROJECT, {"name": name})
    project = data["projectCreate"]
    envs    = _unwrap_edges(project["environments"])
    return project["id"], _pick_prod_env(envs)


# ---------------------------------------------------------------------------
# Service management
# ---------------------------------------------------------------------------

_Q_SERVICES = """
query GetServices($projectId: String!) {
  project(id: $projectId) {
    services { edges { node { id name } } }
  }
}
"""

_M_CREATE_SERVICE = """
mutation CreateService($projectId: String!, $name: String!) {
  serviceCreate(input: { projectId: $projectId, name: $name }) { id name }
}
"""


async def _get_or_create_service(
    client: httpx.AsyncClient,
    token: str,
    project_id: str,
    service_name: str,
) -> str:
    data     = await _gql(client, token, _Q_SERVICES, {"projectId": project_id})
    services = _unwrap_edges(data["project"]["services"])
    for svc in services:
        if svc["name"] == service_name:
            log.info("[RAILWAY] Reusing service %s", svc["id"][:8])
            return svc["id"]

    data = await _gql(client, token, _M_CREATE_SERVICE,
                      {"projectId": project_id, "name": service_name})
    sid = data["serviceCreate"]["id"]
    log.info("[RAILWAY] Created service %s", sid[:8])
    return sid


# ---------------------------------------------------------------------------
# Service domain — get or create the *.up.railway.app public URL
# ---------------------------------------------------------------------------

_Q_SERVICE_INSTANCE = """
query ServiceInstance($serviceId: String!, $environmentId: String!) {
  serviceInstance(serviceId: $serviceId, environmentId: $environmentId) {
    domains {
      serviceDomains { domain }
    }
  }
}
"""

_M_SERVICE_DOMAIN_CREATE = """
mutation ServiceDomainCreate($serviceId: String!, $environmentId: String!) {
  serviceDomainCreate(input: {
    serviceId: $serviceId
    environmentId: $environmentId
  }) {
    domain
  }
}
"""


async def _ensure_service_domain(
    client: httpx.AsyncClient,
    token: str,
    service_id: str,
    env_id: str,
) -> str:
    """Return https://... URL for this service. Creates a domain if none exists."""
    try:
        data = await _gql(client, token, _Q_SERVICE_INSTANCE, {
            "serviceId": service_id, "environmentId": env_id,
        })
        domains = data.get("serviceInstance") or {}
        service_domains = (domains.get("domains") or {}).get("serviceDomains", [])
        if service_domains:
            d = service_domains[0]["domain"]
            return f"https://{d}" if not d.startswith("https") else d
    except Exception as exc:
        log.debug("[RAILWAY] domain query failed: %s — will create", exc)

    # No domain yet — create one
    try:
        data = await _gql(client, token, _M_SERVICE_DOMAIN_CREATE, {
            "serviceId": service_id, "environmentId": env_id,
        })
        d = data["serviceDomainCreate"]["domain"]
        return f"https://{d}" if not d.startswith("https") else d
    except Exception as exc:
        log.warning("[RAILWAY] Could not create domain: %s", exc)
        return ""


# ---------------------------------------------------------------------------
# Tarball — dist/ + Dockerfile + nginx.conf only
# ---------------------------------------------------------------------------

def _add_str(tar: tarfile_mod.TarFile, name: str, content: str) -> None:
    """Add an in-memory string as a file into the tarball."""
    data = content.encode("utf-8")
    info = tarfile_mod.TarInfo(name=name)
    info.size = len(data)
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def _make_tarball(build_dir: Path) -> bytes:
    """
    Build a minimal tarball: dist/ assets + Dockerfile + nginx.conf.

    Railway detects the Dockerfile and uses Docker instead of Nixpacks.
    The nginx image serves the pre-built SPA on port 8080 with SPA routing.

    Falls back to packaging full source (for Nixpacks) if dist/ is missing —
    but deployment will likely fail without a start script.
    """
    dist_dir = build_dir / "dist"

    buf = io.BytesIO()
    with tarfile_mod.open(fileobj=buf, mode="w:gz") as tar:
        # Always include Dockerfile + nginx.conf so Railway uses Docker
        _add_str(tar, "Dockerfile", _DOCKERFILE)
        _add_str(tar, "nginx.conf", _NGINX_CONF)

        if dist_dir.is_dir():
            # Primary path: copy only pre-built assets
            for f in sorted(dist_dir.rglob("*")):
                if f.is_file():
                    arcname = "dist/" + f.relative_to(dist_dir).as_posix()
                    tar.add(str(f), arcname=arcname)
            log.info("[RAILWAY] Tarball: Dockerfile + nginx.conf + dist/ (%d files)",
                     sum(1 for f in dist_dir.rglob("*") if f.is_file()))
        else:
            # Fallback: include source so Railway can attempt a Nixpacks build.
            # Deployment may fail if no `start` script exists in package.json.
            log.warning(
                "[RAILWAY] dist/ not found in %s — falling back to source upload. "
                "Run vite build first for reliable deployment.", build_dir
            )
            for f in sorted(build_dir.rglob("*")):
                if not f.is_file():
                    continue
                parts = f.relative_to(build_dir).parts
                if any(p in _EXCLUDE_DIRS for p in parts):
                    continue
                tar.add(str(f), arcname=str(f.relative_to(build_dir)))

    result = buf.getvalue()
    log.info("[RAILWAY] Tarball total size: %.1f KB", len(result) / 1024)
    return result


# ---------------------------------------------------------------------------
# Upload + Deploy
# ---------------------------------------------------------------------------

# GraphQL mutation to create a pre-signed source upload slot.
# Returns { id, url } where url is a temporary S3 pre-signed PUT URL.
# The id is used as sourceUploadId in deploymentCreate.
# This avoids the graphql-multipart-request-spec ordering requirement of the
# legacy /deployments/uploads REST endpoint (which returned HTTP 400 with
# "Misordered multipart fields; files should follow 'map'").
_M_SOURCE_UPLOAD_CREATE = """
mutation SourceUploadCreate {
  sourceUploadCreate {
    id
    url
  }
}
"""


async def _upload_tarball(
    client: httpx.AsyncClient,
    token: str,
    tarball: bytes,
) -> str:
    """
    Upload tarball to Railway via sourceUploadCreate GraphQL mutation.

    Flow:
      1. sourceUploadCreate → { id, url }  (url is S3 pre-signed PUT endpoint)
      2. PUT tarball directly to url        (no auth header — S3 uses the signature)
      3. Return id for use in deploymentCreate

    The old /deployments/uploads multipart endpoint requires graphql-multipart-request-spec
    field ordering (operations → map → file) and returned HTTP 400 when only the file
    field was sent without the preceding 'map' field.
    """
    # Step 1: create upload slot and get pre-signed URL
    data      = await _gql(client, token, _M_SOURCE_UPLOAD_CREATE, {})
    src       = data.get("sourceUploadCreate") or {}
    upload_id = src.get("id", "")
    upload_url = src.get("url", "")

    if not upload_id or not upload_url:
        raise RuntimeError(
            f"Railway sourceUploadCreate returned unexpected response: {src}"
        )
    log.info("[RAILWAY] sourceUploadCreate id=%s url=%s…", upload_id[:12], upload_url[:60])

    # Step 2: PUT tarball to pre-signed URL — S3 pre-signed URLs don't use the Bearer token
    upload_resp = await client.put(
        upload_url,
        content=tarball,
        headers={"Content-Type": "application/gzip"},
        timeout=180.0,
    )
    if not upload_resp.is_success:
        raise RuntimeError(
            f"Railway source upload PUT failed HTTP {upload_resp.status_code}: "
            f"{upload_resp.text[:300]}"
        )

    log.info("[RAILWAY] Upload PUT → HTTP %d (%.1f KB)", upload_resp.status_code, len(tarball) / 1024)
    return upload_id


_M_CREATE_DEPLOYMENT = """
mutation CreateDeployment($serviceId: String!, $environmentId: String!, $uploadId: String!) {
  deploymentCreate(input: {
    serviceId:      $serviceId
    environmentId:  $environmentId
    sourceUploadId: $uploadId
  }) { id }
}
"""

_Q_DEPLOYMENT_STATUS = """
query DeploymentStatus($id: String!) {
  deployment(id: $id) {
    id
    status
    url
    staticUrl
    meta { serviceId environmentId }
  }
}
"""


async def _create_deployment(
    client: httpx.AsyncClient,
    token: str,
    service_id: str,
    env_id: str,
    upload_id: str,
) -> str:
    data = await _gql(client, token, _M_CREATE_DEPLOYMENT, {
        "serviceId":     service_id,
        "environmentId": env_id,
        "uploadId":      upload_id,
    })
    return data["deploymentCreate"]["id"]


async def _poll_deployment(
    client: httpx.AsyncClient,
    token: str,
    deployment_id: str,
) -> None:
    """
    Poll deployment status until terminal state.
    Raises RuntimeError on FAILED/CRASHED/REMOVED.
    Returns normally on SUCCESS.

    Note: we do NOT return a URL here — the URL comes from _ensure_service_domain
    called before deployment starts. deployment.url is null for Docker/Nixpacks.
    """
    deadline = asyncio.get_event_loop().time() + _DEPLOY_TIMEOUT
    # Non-terminal states we keep polling through
    in_progress = {"INITIALIZING", "BUILDING", "DEPLOYING", "QUEUED", "WAITING", "SLEEPING"}
    failure_states = {"FAILED", "CRASHED", "REMOVED"}

    prev_status = ""
    while asyncio.get_event_loop().time() < deadline:
        try:
            data   = await _gql(client, token, _Q_DEPLOYMENT_STATUS, {"id": deployment_id})
            dep    = data.get("deployment") or {}
            status = dep.get("status", "UNKNOWN")
        except Exception as exc:
            log.warning("[RAILWAY] Poll query failed: %s — retrying", exc)
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        if status != prev_status:
            log.info("[RAILWAY] deployment=%s status=%s", deployment_id[:12], status)
            prev_status = status

        if status == "SUCCESS":
            return

        if status in failure_states:
            raise RuntimeError(
                f"Railway deployment {deployment_id[:12]} ended with status={status}. "
                "Check Railway dashboard for build logs."
            )

        if status not in in_progress:
            log.warning("[RAILWAY] Unknown deployment status: %s — continuing to poll", status)

        await asyncio.sleep(_POLL_INTERVAL)

    raise RuntimeError(
        f"Railway deployment {deployment_id[:12]} timed out after {_DEPLOY_TIMEOUT}s. "
        "The container may still be starting — check Railway dashboard."
    )


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _unwrap_edges(connection: dict) -> list[dict]:
    return [e["node"] for e in connection.get("edges", []) if "node" in e]


def _pick_prod_env(envs: list[dict]) -> str:
    for e in envs:
        if e.get("name", "").lower() in ("production", "prod"):
            return e["id"]
    return envs[0]["id"] if envs else ""
