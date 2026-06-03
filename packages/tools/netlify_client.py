"""
packages/tools/netlify_client.py
Netlify deployment client for generated SaaS frontends.

Why Netlify as an alternative to Railway:
  - Simple API: zip the dist/ folder → POST → get a URL
  - No GraphQL, no project IDs, no environment IDs
  - Free tier: unlimited static deploys
  - Perfect for React + Vite SPAs
  - Handles SPA routing natively (serves index.html for all 404s)

Setup (one-time):
  1. Go to https://app.netlify.com → User Settings → Applications → New access token
  2. Set NETLIFY_TOKEN=<token> in Railway Variables
  3. Deploy endpoint will automatically use Netlify when NETLIFY_TOKEN is set

Required env var: NETLIFY_TOKEN
Optional env var: NETLIFY_SITE_ID  (reuse an existing site instead of creating new one per venture)
"""
from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

_API_BASE = "https://api.netlify.com/api/v1"


def netlify_available() -> bool:
    token = os.getenv("NETLIFY_TOKEN", "")
    return bool(token and len(token) > 10 and "your_" not in token)


def _auth_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('NETLIFY_TOKEN', '')}",
        "Content-Type": "application/zip",
    }


def _make_zip(dist_dir: Path) -> bytes:
    """Zip all files in dist/ for Netlify deployment."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(dist_dir.rglob("*")):
            if f.is_file():
                zf.write(f, arcname=f.relative_to(dist_dir))
    return buf.getvalue()


async def deploy_to_netlify(venture_id: str, build_dir: Path) -> str:
    """
    Deploy the dist/ folder to Netlify as a new site (or update existing).

    Returns the live https://xxx.netlify.app URL.
    Raises RuntimeError on failure.
    """
    dist_dir = build_dir / "dist"
    if not dist_dir.is_dir():
        raise RuntimeError(
            f"dist/ not found at {dist_dir}. "
            "Run vite build first (QA_REQUIRE_VITE_BUILD=true)."
        )

    site_id = os.getenv("NETLIFY_SITE_ID", "")
    zip_bytes = _make_zip(dist_dir)
    log.info("[NETLIFY] Zipped dist/ | size=%.1f KB", len(zip_bytes) / 1024)

    async with httpx.AsyncClient(timeout=120.0) as client:
        if site_id:
            # Update existing site
            resp = await client.post(
                f"{_API_BASE}/sites/{site_id}/deploys",
                content=zip_bytes,
                headers=_auth_headers(),
            )
        else:
            # Create new site (name from venture_id slug)
            site_name = f"aisq-{venture_id[:20].replace('_', '-')}"
            resp = await client.post(
                f"{_API_BASE}/sites",
                content=zip_bytes,
                headers={**_auth_headers(), "X-Netlify-Site-Name": site_name},
            )

        if not resp.is_success:
            raise RuntimeError(
                f"Netlify deploy failed HTTP {resp.status_code}: {resp.text[:300]}"
            )

        data = resp.json()
        # Prefer canonical site URL (ssl_url) over deploy-preview URL (deploy_ssl_url).
        # Deploy-preview URLs are rate-limited on Netlify free tier (429).
        # The site URL (luminous-souffle-xxx.netlify.app) has no such limit.
        deploy_id = data.get("deploy_id") or data.get("id", "")
        ssl_url   = data.get("ssl_url") or data.get("deploy_ssl_url") or data.get("url", "")

        if ssl_url:
            log.info("[NETLIFY] ✓ Deployed | url=%s", ssl_url)
            return ssl_url

        # Poll for SSL URL if not immediately available
        if deploy_id:
            return await _poll_netlify_deploy(client, deploy_id)

        raise RuntimeError(f"Netlify returned no URL: {data}")


async def _poll_netlify_deploy(client: httpx.AsyncClient, deploy_id: str) -> str:
    import asyncio
    for _ in range(30):   # 30 × 5s = 2.5 min
        resp = await client.get(
            f"{_API_BASE}/deploys/{deploy_id}",
            headers={"Authorization": f"Bearer {os.getenv('NETLIFY_TOKEN', '')}"},
        )
        if resp.is_success:
            data  = resp.json()
            state = data.get("state", "")
            url   = data.get("deploy_ssl_url") or data.get("ssl_url", "")
            log.info("[NETLIFY] Poll state=%s", state)
            if state == "ready" and url:
                # Always return canonical site URL, never the deploy-preview URL
                canonical = data.get("ssl_url") or url
                # CDN propagation delay — new sites get 429 for ~30s after "ready"
                log.info("[NETLIFY] Deploy ready — waiting 20s for CDN propagation")
                await asyncio.sleep(20)
                return canonical
            if state in ("error", "failed"):
                raise RuntimeError(f"Netlify deploy {deploy_id} failed: {data.get('error_message')}")
        await asyncio.sleep(5)
    raise RuntimeError("Netlify deploy timed out after 2.5 minutes")
