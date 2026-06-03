"""
packages/tools/railway_client.py
Railway REST + GraphQL API client for programmatic SaaS deployments.

Deployment flow
---------------
1. Validate token with a `me` query first (fast auth check)
2. Get or create one Railway project ("ai-squadron") per org
3. Get or create a service per venture_id inside that project
4. Pack build_dir into a .tar.gz (node_modules / dist excluded)
5. POST tarball to Railway's upload endpoint → uploadId
6. GraphQL deploymentCreate(serviceId, environmentId, uploadId)
7. Poll deployment.status until SUCCESS or terminal failure
8. Return the live HTTPS URL

Required env var: RAILWAY_TOKEN  OR  RAILWAY_API_TOKEN
Optional env var: RAILWAY_PROJECT_ID  (if omitted, project is auto-managed)

Schema: Railway Backboard GraphQL v2 (2025 — edges/node connection style)
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


def _ssl_verify() -> bool:
    return os.getenv("HTTPX_SSL_VERIFY", "true").lower() != "false"

_GRAPHQL_URL   = "https://backboard.railway.app/graphql/v2"
_UPLOAD_URL    = "https://backboard.railway.app/deployments/uploads"
_POLL_INTERVAL = 5    # seconds between status checks
_DEPLOY_TIMEOUT = 300  # 5 minutes max

_EXCLUDE_DIRS = {"node_modules", ".git", ".cache", "__pycache__"}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def _get_railway_token() -> str:
    """Accept RAILWAY_TOKEN or RAILWAY_API_TOKEN — whichever is set."""
    return os.getenv("RAILWAY_TOKEN", "") or os.getenv("RAILWAY_API_TOKEN", "")


def railway_available() -> bool:
    """True when RAILWAY_TOKEN (or RAILWAY_API_TOKEN) is configured."""
    token = _get_railway_token()
    return bool(token and len(token) > 10 and not token.startswith("your_"))


async def deploy_to_railway(venture_id: str, build_dir: Path) -> str:
    """
    Deploy a Vite build directory to Railway.
    Returns the live HTTPS URL on success.
    Raises RuntimeError if the deployment fails or times out.

    Supports two token types:
      User Token  (Account Settings → Tokens): auto-manages projects.
      Project Token (Project → Settings → Tokens): set RAILWAY_PROJECT_ID too.
    """
    token        = _get_railway_token()
    service_name = venture_id[:30]
    # Railway auto-injects these into every container at runtime.
    # If both are present we skip all project-level GraphQL (the only queries
    # that fail with a Project Token). User Token only needed when neither is set.
    forced_pid = os.getenv("RAILWAY_PROJECT_ID", "")
    forced_env = os.getenv("RAILWAY_ENVIRONMENT_ID", "")

    async with httpx.AsyncClient(timeout=45.0, verify=_ssl_verify()) as client:
        # 1. Project + environment — 3-tier lookup
        if forced_pid and forced_env:
            # Best path: both auto-injected by Railway OR set manually.
            # Zero project-level GraphQL needed — works with Project Tokens.
            project_id, env_id = forced_pid, forced_env
            log.info("[RAILWAY] Auto-injected project=%s env=%s",
                     project_id[:8], env_id[:8])
        elif forced_pid:
            # Have project ID — one small query to resolve environment.
            data = await _gql(client, token, _Q_PROJECT_BY_ID, {"id": forced_pid})
            envs = _unwrap_edges(data["project"]["environments"])
            project_id, env_id = forced_pid, _pick_prod_env(envs)
            log.info("[RAILWAY] project=%s env=%s (env resolved)", project_id[:8], env_id[:8])
        else:
            # No project ID — requires User Token (Account Settings → Tokens).
            # Project Tokens cannot query 'me { projects }' and will fail here.
            log.info("[RAILWAY] No RAILWAY_PROJECT_ID — User Token auto-discovery")
            project_id, env_id = await _get_or_create_project(client, token, "ai-squadron")
            log.info("[RAILWAY] project=%s env=%s", project_id[:8], env_id[:8])

        # 2. Service
        service_id = await _get_or_create_service(client, token, project_id, service_name)
        log.info("[RAILWAY] service=%s (%s)", service_id[:8], service_name)

        # 3. Tarball
        tarball   = _make_tarball(build_dir)
        log.info("[RAILWAY] Tarball size=%.1f KB", len(tarball) / 1024)

        # 4. Upload
        upload_id = await _upload_tarball(client, token, tarball)
        log.info("[RAILWAY] Uploaded → uploadId=%s", upload_id[:8])

        # 5. Deploy
        deploy_id = await _create_deployment(client, token, service_id, env_id, upload_id)
        log.info("[RAILWAY] Deployment queued → deploymentId=%s", deploy_id[:8])

        # 6. Poll
        url = await _poll_deployment(client, token, deploy_id)
        return url or f"https://{service_name}.up.railway.app"


# ---------------------------------------------------------------------------
# GraphQL helper — captures full error body on failure
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

    # Capture response body BEFORE raise_for_status so we can log it
    try:
        body_text = resp.text
    except Exception:
        body_text = "<unreadable>"

    if not resp.is_success:
        log.error("[RAILWAY] HTTP %d from GraphQL | body=%s", resp.status_code, body_text[:400])
        raise RuntimeError(
            f"Railway API returned HTTP {resp.status_code}: {body_text[:300]}"
        )

    body = resp.json()
    if errors := body.get("errors"):
        msg = errors[0].get("message", str(errors))
        log.error("[RAILWAY] GraphQL error: %s", msg)
        raise RuntimeError(f"Railway GraphQL error: {msg}")

    return body["data"]


# ---------------------------------------------------------------------------
# Project management — uses edge/node connection style (Railway 2025 schema)
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
    """
    Returns (project_id, production_env_id).
    Requires a User Token (Account Settings → Tokens).
    For Project Tokens, set RAILWAY_PROJECT_ID and this function is bypassed.
    """
    try:
        data = await _gql(client, token, _Q_MY_PROJECTS, {})
    except Exception as exc:
        raise RuntimeError(
            "Railway 'me' query failed — this requires a User Token, not a Project Token.\n"
            "Fix: Account avatar → Account Settings → Tokens → New Token (copy the value).\n"
            "OR: set RAILWAY_PROJECT_ID env var and use a Project Token instead.\n"
            f"Detail: {exc}"
        ) from exc

    projects = _unwrap_edges(data["me"]["projects"])
    for project in projects:
        if project["name"] == name:
            envs = _unwrap_edges(project["environments"])
            return project["id"], _pick_prod_env(envs)

    # Create new project
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
            return svc["id"]

    data = await _gql(client, token, _M_CREATE_SERVICE,
                      {"projectId": project_id, "name": service_name})
    return data["serviceCreate"]["id"]


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _unwrap_edges(connection: dict) -> list[dict]:
    """Convert Railway's edge/node connection format to a plain list."""
    edges = connection.get("edges", [])
    return [e["node"] for e in edges if "node" in e]


def _pick_prod_env(envs: list[dict]) -> str:
    for e in envs:
        if e.get("name", "").lower() in ("production", "prod"):
            return e["id"]
    return envs[0]["id"] if envs else ""


# ---------------------------------------------------------------------------
# Tarball
# ---------------------------------------------------------------------------

def _make_tarball(build_dir: Path) -> bytes:
    buf = io.BytesIO()
    with tarfile_mod.open(fileobj=buf, mode="w:gz") as tar:
        for file_path in sorted(build_dir.rglob("*")):
            if not file_path.is_file():
                continue
            parts = file_path.relative_to(build_dir).parts
            if any(part in _EXCLUDE_DIRS for part in parts):
                continue
            tar.add(str(file_path), arcname=str(file_path.relative_to(build_dir)))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Upload + Deploy
# ---------------------------------------------------------------------------

async def _upload_tarball(
    client: httpx.AsyncClient,
    token: str,
    tarball: bytes,
) -> str:
    resp = await client.post(
        _UPLOAD_URL,
        files={"file": ("source.tar.gz", tarball, "application/gzip")},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120.0,
        verify=_ssl_verify(),
    )
    if not resp.is_success:
        raise RuntimeError(f"Railway upload failed HTTP {resp.status_code}: {resp.text[:300]}")
    data      = resp.json()
    upload_id = data.get("uploadId") or data.get("id", "")
    if not upload_id:
        raise RuntimeError(f"Railway upload returned no uploadId: {data}")
    return upload_id


_M_CREATE_DEPLOYMENT = """
mutation CreateDeployment($serviceId: String!, $environmentId: String!, $uploadId: String!) {
  deploymentCreate(input: {
    serviceId: $serviceId
    environmentId: $environmentId
    sourceUploadId: $uploadId
  }) { id }
}
"""

_Q_DEPLOYMENT_STATUS = """
query DeploymentStatus($id: String!) {
  deployment(id: $id) { id status url staticUrl }
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
) -> str:
    deadline = asyncio.get_event_loop().time() + _DEPLOY_TIMEOUT
    terminal = {"SUCCESS", "FAILED", "CRASHED", "REMOVED"}

    while asyncio.get_event_loop().time() < deadline:
        data   = await _gql(client, token, _Q_DEPLOYMENT_STATUS, {"id": deployment_id})
        dep    = data["deployment"]
        status = dep["status"]
        log.info("[RAILWAY] Poll | deploymentId=%s status=%s", deployment_id[:8], status)

        if status == "SUCCESS":
            return dep.get("url") or dep.get("staticUrl") or ""
        if status in terminal:
            raise RuntimeError(f"Deployment {deployment_id[:8]} ended with status={status}")

        await asyncio.sleep(_POLL_INTERVAL)

    raise RuntimeError(
        f"Deployment {deployment_id[:8]} timed out after {_DEPLOY_TIMEOUT}s"
    )
