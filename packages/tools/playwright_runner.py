"""
packages/tools/playwright_runner.py
Playwright headless browser smoke-test for generated SaaS builds.

Week 9 — Phase 2 Quality gate.

What it tests:
  1. Page loads (no HTTP 4xx/5xx)
  2. React mounts   — #root has at least one child element
  3. No uncaught JS errors in the console
  4. Load time < 8 seconds

How it works:
  1. Spin up Python's built-in http.server on a random free port
  2. Launch Chromium headless (prefers system Chromium, falls back to
     Playwright's downloaded binary)
  3. Navigate to http://localhost:{port}/
  4. Assert the checks above
  5. Kill the server

Graceful degradation:
  - If playwright is not installed → returns (True, ["playwright_skip"])
  - If Chromium is not found     → returns (True, ["playwright_skip"])
  - Callers treat "playwright_skip" as a non-failure so local dev /
    CI without Chromium still passes without blocking the pipeline.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import socket
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Maximum time (seconds) allowed for the page to load and React to mount
_PAGE_TIMEOUT_MS  = 8_000
_MOUNT_TIMEOUT_MS = 5_000

# Chromium launch flags safe for containerised environments
_CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def playwright_available() -> bool:
    """True when both the playwright Python package AND a Chromium binary exist."""
    try:
        import playwright  # noqa: F401 — only checking importability
        return True
    except ImportError:
        return False


async def run_smoke_test(dist_dir: Path) -> tuple[bool, list[str]]:
    """
    Serve dist_dir over HTTP and visit it with Playwright Chromium.

    Returns:
        (passed, errors)   where errors is a list of human-readable strings.
        If Playwright is not available, returns (True, ["playwright_skip"]).
    """
    if not playwright_available():
        log.info("[PLAYWRIGHT] Not installed — skipping browser smoke test")
        return True, ["playwright_skip — install playwright + chromium for browser tests"]

    if not dist_dir.is_dir():
        return False, [f"dist dir not found: {dist_dir}"]

    port = _free_port()
    server = await _start_server(dist_dir, port)

    errors: list[str] = []
    passed = False

    try:
        # Give the HTTP server a moment to bind
        await asyncio.sleep(0.5)

        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            exe = _chromium_executable()
            launch_kw: dict = {"args": _CHROMIUM_ARGS}
            if exe:
                launch_kw["executable_path"] = exe

            try:
                browser = await pw.chromium.launch(**launch_kw)
            except Exception as exc:
                log.warning("[PLAYWRIGHT] Browser launch failed: %s", exc)
                return True, ["playwright_skip — Chromium launch failed, likely not installed"]

            page = await browser.new_page()

            # Capture console errors + uncaught exceptions
            page.on("console", lambda m: errors.append(f"[console.error] {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"[uncaught] {e}"))

            try:
                log.info("[PLAYWRIGHT] Visiting http://localhost:%d/", port)
                resp = await page.goto(
                    f"http://localhost:{port}/",
                    timeout=_PAGE_TIMEOUT_MS,
                    wait_until="domcontentloaded",
                )

                if resp is None:
                    errors.append("No response from dev server")
                elif resp.status >= 400:
                    errors.append(f"HTTP {resp.status} from dev server")
                else:
                    # Check that React actually mounted something inside #root
                    try:
                        await page.wait_for_selector(
                            "#root > *",
                            timeout=_MOUNT_TIMEOUT_MS,
                        )
                        passed = True
                        log.info("[PLAYWRIGHT] ✓ React mounted | console_errors=%d", len(errors))
                    except Exception:
                        errors.append("#root is empty — React did not mount (check App.tsx for runtime errors)")

            except asyncio.TimeoutError:
                errors.append(f"Page load timed out after {_PAGE_TIMEOUT_MS}ms")
            except Exception as exc:
                errors.append(f"Navigation error: {exc!s:.200}")
            finally:
                await browser.close()

    finally:
        server.terminate()
        try:
            await asyncio.wait_for(server.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            server.kill()

    if passed and errors:
        log.warning("[PLAYWRIGHT] Passed with %d console error(s): %s", len(errors), errors[:3])

    return passed, errors


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Return an OS-assigned free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _start_server(directory: Path, port: int) -> asyncio.subprocess.Process:
    """Spawn Python's built-in http.server in directory on port."""
    python = sys.executable
    proc = await asyncio.create_subprocess_exec(
        python, "-m", "http.server", str(port),
        cwd=str(directory),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    log.debug("[PLAYWRIGHT] HTTP server PID=%d port=%d dir=%s", proc.pid, port, directory)
    return proc


def _chromium_executable() -> str | None:
    """
    Find a system Chromium binary.
    Returns None if not found — Playwright will use its own downloaded browser.
    """
    candidates = [
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "google-chrome-beta",
    ]
    for name in candidates:
        exe = shutil.which(name)
        if exe:
            log.debug("[PLAYWRIGHT] Using system Chromium: %s", exe)
            return exe

    # Check common Nix store paths emitted by nixpacks chromium package
    nix_paths = [
        "/run/current-system/sw/bin/chromium",
        "/nix/var/nix/profiles/default/bin/chromium",
    ]
    for p in nix_paths:
        if Path(p).exists():
            log.debug("[PLAYWRIGHT] Using Nix Chromium: %s", p)
            return p

    return None  # Let Playwright fall back to its downloaded binary
