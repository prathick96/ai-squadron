"""
packages/tools/railway_client.py
Railway REST + GraphQL API client for programmatic SaaS deployments.

Deployment flow
---------------
1. Get or create one Railway project for the whole AI Squadron org
   (uses RAILWAY_PROJECT_ID if set, otherwise finds/creates "ai-squadron")
2. Get or create a service per venture_id inside that project
3. Pack build_dir into a .tar.gz (node_modules excluded)
4. POST tarball to Railway's upload endpoint → uploadId
5. GraphQL deploymentCreate(serviceId, environmentId, uploadId)
6. Poll deployment.status until SUCCESS or terminal failure
7. Return the live HTTPS URL

Required env var: RAILWAY_TOKEN
Optional env var: RAILWAY_PROJECT_ID  (if omitted, project is auto-managed)
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

# Directories excluded from the deployment tarball
_EXCLUDE_DIRS = {"node_modules", ".git", ".cache", "dist", "__pycache__"}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def railway_available() -> bool:
    """True when RAILWAY_TOKEN is configured and looks like a real token."""
    token = os.getenv("RAILWAY_TOKEN", "")
    return bool(token and len(token) > 10 and not token.startswith("your_"))


async def deploy_to_railway(venture_id: str, build_dir: Path) -> str:
    """
    Deploy a Vite build directory to Railway.

    Returns the live HTTPS URL on success.
    Raises RuntimeError if the deployment fails or times out.
    """
    token       = _token()
    project_name = "ai-squadron"
    service_name = venture_id[:30]

    async with httpx.AsyncClient(timeout=30.0, verify=_ssl_verify()) as client:
        project_id, env_id = await _get_or_create_project(client, token, project_name)
        service_id         = await _get_or_create_service(client, token, project_id, service_name)
        log.info("[RAILWAY] project=%s service=%s env=%s",
                 project_id[:8], service_id[:8], env_id[:8])

        tarball     = _make_tarball(build_dir)
        log.info("[RAILWAY] Tarball ready | size=%.1f KB", len(tarball) / 1024)

        upload_id   = await _upload_tarball(client, token, tarball)
        log.info("[RAILWAY] Upload complete | uploadId=%s", upload_id[:8])

        deploy_id   = await _create_deployment(client, token, service_id, env_id, upload_id)
        log.info("[RAILWAY] Deployment queued | deploymentId=%s", deploy_id[:8])

        url         = await _poll_deployment(client, token, deploy_id)
        return url or f"https://{service_name}.up.railway.app"


# ---------------------------------------------------------------------------
# Internal — GraphQL helpers
# ---------------------------------------------------------------------------

def _token() -> str:
    return os.getenv("RAILWAY_TOKEN", "")


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def _gql(
    client: httpx.AsyncClient,
    token: str,
    query: str,
    variables: dict,
) -> dict:
    resp = await client.post(
        _GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers=_auth_headers(token),
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()
    if errors := body.get("errors"):
        raise RuntimeError(f"Railway GraphQL error: {errors[0].get('message', errors)}")
    return body["data"]


# ---------------------------------------------------------------------------
# Internal — Project / service management
# ---------------------------------------------------------------------------

_Q_PROJECTS = """
query ListProjects {
  projects { nodes { id name environments { nodes { id name } } services { nodes { id name } } } }
}
"""

_M_CREATE_PROJECT = """
mutation CreateProject($name: String!) {
  projectCreate(input: { name: $name, isPublic: false }) {
    id
    environments { nodes { id name } }
  }
}
"""

_M_CREATE_SERVICE = """
mutation CreateService($projectId: ID!, $name: String!) {
  serviceCreate(input: { projectId: $projectId, name: $name }) { id name }
}
"""


async def _get_or_create_project(
    client: httpx.AsyncClient,
    token: str,
    name: str,
) -> tuple[str, str]:
    """Returns (project_id, production_env_id)."""
    forced_id = os.getenv("RAILWAY_PROJECT_ID", "")
    if forced_id:
        data = await _gql(client, token, """
            query GetProject($id: ID!) {
              project(id: $id) { id environments { nodes { id name } } }
            }
        """, {"id": forced_id})
        envs = data["project"]["environments"]["nodes"]
        env_id = _pick_prod_env(envs)
        return forced_id, env_id

    data = await _gql(client, token, _Q_PROJECTS, {})
    for project in data.get("projects", {}).get("nodes", []):
        if project["name"] == name:
            envs = project["environments"]["nodes"]
            return project["id"], _pick_prod_env(envs)

    # Create new project
    data = await _gql(client, token, _M_CREATE_PROJECT, {"name": name})
    project = data["projectCreate"]
    envs = project["environments"]["nodes"]
    return project["id"], _pick_prod_env(envs)


async def _get_or_create_service(
    client: httpx.AsyncClient,
    token: str,
    project_id: str,
    service_name: str,
) -> str:
    """Returns service_id, creating the service if it doesn't exist."""
    data = await _gql(client, token, """
        query GetServices($projectId: ID!) {
          project(id: $projectId) { services { nodes { id name } } }
        }
    """, {"projectId": project_id})

    for svc in data["project"]["services"]["nodes"]:
        if svc["name"] == service_name:
            return svc["id"]

    data = await _gql(client, token, _M_CREATE_SERVICE,
                      {"projectId": project_id, "name": service_name})
    return data["serviceCreate"]["id"]


def _pick_prod_env(envs: list[dict]) -> str:
    """Return production environment id, or first available."""
    for e in envs:
        if e["name"].lower() in ("production", "prod"):
            return e["id"]
    return envs[0]["id"] if envs else ""


# ---------------------------------------------------------------------------
# Internal — Tarball
# ---------------------------------------------------------------------------

def _make_tarball(build_dir: Path) -> bytes:
    """
    Pack build_dir into an in-memory .tar.gz, excluding node_modules and other
    large directories that Railway doesn't need to receive.
    """
    buf = io.BytesIO()
    with tarfile_mod.open(fileobj=buf, mode="w:gz") as tar:
        for file_path in sorted(build_dir.rglob("*")):
            if not file_path.is_file():
                continue
            # Skip any path that contains an excluded directory name
            parts = file_path.relative_to(build_dir).parts
            if any(part in _EXCLUDE_DIRS for part in parts):
                continue
            tar.add(str(file_path), arcname=str(file_path.relative_to(build_dir)))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Internal — Upload + Deploy
# ---------------------------------------------------------------------------

async def _upload_tarball(
    client: httpx.AsyncClient,
    token: str,
    tarball: bytes,
) -> str:
    """POST tarball to Railway's upload endpoint. Returns uploadId."""
    resp = await client.post(
        _UPLOAD_URL,
        files={"file": ("source.tar.gz", tarball, "application/gzip")},
        headers={"Authorization": f"Bearer {token}"},
        timeout=120.0,
        verify=_ssl_verify(),
    )
    resp.raise_for_status()
    data = resp.json()
    upload_id = data.get("uploadId") or data.get("id", "")
    if not upload_id:
        raise RuntimeError(f"Railway upload returned no uploadId: {data}")
    return upload_id


_M_CREATE_DEPLOYMENT = """
mutation CreateDeployment($serviceId: ID!, $environmentId: ID!, $uploadId: ID!) {
  deploymentCreate(input: {
    serviceId: $serviceId,
    environmentId: $environmentId,
    uploadId: $uploadId
  }) { id }
}
"""

_Q_DEPLOYMENT_STATUS = """
query DeploymentStatus($id: ID!) {
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
    """Create a Railway deployment from an upload. Returns deployment_id."""
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
    """
    Poll deployment status every _POLL_INTERVAL seconds.
    Returns the live URL on SUCCESS; raises RuntimeError on failure.
    """
    deadline = asyncio.get_event_loop().time() + _DEPLOY_TIMEOUT
    terminal = {"SUCCESS", "FAILED", "CRASHED", "REMOVED"}

    while asyncio.get_event_loop().time() < deadline:
        data   = await _gql(client, token, _Q_DEPLOYMENT_STATUS, {"id": deployment_id})
        dep    = data["deployment"]
        status = dep["status"]
        log.info("[RAILWAY] Deployment %s | status=%s", deployment_id[:8], status)

        if status == "SUCCESS":
            return dep.get("url") or dep.get("staticUrl") or ""
        if status in terminal:
            raise RuntimeError(f"Deployment {deployment_id[:8]} ended with status={status}")

        await asyncio.sleep(_POLL_INTERVAL)

    raise RuntimeError(
        f"Deployment {deployment_id[:8]} timed out after {_DEPLOY_TIMEOUT}s"
    )
