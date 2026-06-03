"""
packages/tools/vercel_client.py
Vercel deployment client for generated SaaS static frontends.

Deployment flow
---------------
1. Walk dist/ and compute SHA-1 hash of every file
2. Upload files to Vercel's file cache (skipped if already cached)
3. POST deployment manifest — references file hashes + project settings
4. Poll deployment status until READY or ERROR
5. Return the canonical https://{name}.vercel.app URL

Required env var: VERCEL_TOKEN  (from vercel.com → Account Settings → Tokens)
Optional env var: VERCEL_TEAM_ID  (for team deployments — leave empty for personal)

Token setup:
  1. Go to vercel.com → click your avatar → Account Settings → Tokens
  2. New Token → name it "AI Squadron" → Full Account access
  3. Set VERCEL_TOKEN=<token> in Railway Variables
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_API = "https://api.vercel.com"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def vercel_available() -> bool:
    token = os.getenv("VERCEL_TOKEN", "")
    return bool(token and len(token) > 10 and "your_" not in token)


async def deploy_to_vercel(venture_id: str, build_dir: Path) -> str:
    """
    Deploy the dist/ folder to Vercel as a static site.
    Returns the canonical https://{name}.vercel.app URL.
    """
    dist_dir = build_dir / "dist"
    if not dist_dir.is_dir():
        raise RuntimeError(
            f"dist/ not found at {dist_dir}. "
            "Run vite build first (QA_REQUIRE_VITE_BUILD=true)."
        )

    token    = os.getenv("VERCEL_TOKEN", "")
    team_id  = os.getenv("VERCEL_TEAM_ID", "")
    site_name = f"aisq-{venture_id[:24].replace('_', '-')}"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }

    # Add team_id to query params when deploying to a team
    qs = f"?teamId={team_id}" if team_id else ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 1. Collect files + compute SHA-1 hashes
        files_meta = _collect_files(dist_dir)
        log.info("[VERCEL] Collected %d files | site=%s", len(files_meta), site_name)

        # 2. Upload files (Vercel caches by SHA-1 — already-uploaded files are skipped)
        for meta in files_meta:
            await _upload_file(client, token, team_id, meta["sha"], meta["bytes"])
        log.info("[VERCEL] File upload complete")

        # 3. Create deployment
        body = {
            "name": site_name,
            "files": [
                {"file": m["path"], "sha": m["sha"], "size": m["size"]}
                for m in files_meta
            ],
            "target": "production",
            "projectSettings": {
                "framework": None,        # plain static site
                "buildCommand": None,
                "outputDirectory": None,
                "installCommand": None,
                "devCommand": None,
            },
        }

        resp = await client.post(f"{_API}/v13/deployments{qs}", json=body, headers=headers)
        if not resp.is_success:
            raise RuntimeError(
                f"Vercel deployments API returned HTTP {resp.status_code}: {resp.text[:400]}"
            )

        data      = resp.json()
        deploy_id = data.get("id", "")
        url       = data.get("url", "")
        log.info("[VERCEL] Deployment created | id=%s url=%s", deploy_id[:12], url)

        # 4. Poll until ready
        final_url = await _poll_deployment(client, headers, qs, deploy_id, url)
        return f"https://{final_url}" if final_url and not final_url.startswith("https") else final_url


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _collect_files(dist_dir: Path) -> list[dict]:
    """Walk dist/ and return list of {path, sha, size, bytes}."""
    result = []
    for f in sorted(dist_dir.rglob("*")):
        if not f.is_file():
            continue
        raw  = f.read_bytes()
        result.append({
            "path":  f.relative_to(dist_dir).as_posix(),
            "sha":   _sha1(raw),
            "size":  len(raw),
            "bytes": raw,
        })
    return result


async def _upload_file(
    client: httpx.AsyncClient,
    token: str,
    team_id: str,
    sha: str,
    data: bytes,
) -> None:
    """Upload one file to Vercel's file cache (idempotent — uses SHA-1 dedup)."""
    qs = f"?teamId={team_id}" if team_id else ""
    resp = await client.put(
        f"{_API}/v2/files{qs}",
        content=data,
        headers={
            "Authorization":  f"Bearer {token}",
            "Content-Type":   "application/octet-stream",
            "Content-Length": str(len(data)),
            "x-vercel-digest": sha,
        },
        timeout=60.0,
    )
    # 200 = uploaded, 409 = already exists (both are fine)
    if resp.status_code not in (200, 201, 409):
        raise RuntimeError(
            f"Vercel file upload failed HTTP {resp.status_code}: {resp.text[:200]}"
        )


async def _poll_deployment(
    client: httpx.AsyncClient,
    headers: dict,
    qs: str,
    deploy_id: str,
    initial_url: str,
    timeout_s: int = 300,
) -> str:
    """Poll deployment status until READY or ERROR. Returns the deployment URL."""
    deadline  = asyncio.get_event_loop().time() + timeout_s
    ready_states = {"READY"}
    error_states = {"ERROR", "CANCELED"}

    while asyncio.get_event_loop().time() < deadline:
        resp = await client.get(
            f"{_API}/v13/deployments/{deploy_id}{qs}", headers=headers
        )
        if resp.is_success:
            data   = resp.json()
            state  = data.get("readyState") or data.get("state", "")
            url    = data.get("url") or initial_url
            log.info("[VERCEL] Poll deploy_id=%s state=%s", deploy_id[:10], state)

            if state in ready_states:
                log.info("[VERCEL] ✓ Deployment ready | url=%s", url)
                return url
            if state in error_states:
                err = data.get("errorMessage") or state
                raise RuntimeError(f"Vercel deployment failed: {err}")

        await asyncio.sleep(5)

    raise RuntimeError(f"Vercel deployment {deploy_id[:10]} timed out after {timeout_s}s")
