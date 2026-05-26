"""
scripts/youtube_auth.py
One-time OAuth2 authorization flow to obtain a YouTube refresh token.

Run this ONCE, paste the printed YOUTUBE_REFRESH_TOKEN into .env,
and the publishing pipeline will use it for all subsequent uploads.

Usage:
    python scripts/youtube_auth.py

Requires .env to contain:
    YOUTUBE_CLIENT_ID
    YOUTUBE_CLIENT_SECRET
"""
from __future__ import annotations

import os
import sys
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Load .env from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv()

import httpx

_CLIENT_ID     = os.getenv("YOUTUBE_CLIENT_ID", "")
_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
_REDIRECT_URI  = "http://localhost:8080"
_SCOPES        = "https://www.googleapis.com/auth/youtube.upload"

_auth_code: str = ""


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = dict(urllib.parse.parse_qsl(parsed.query))
        _auth_code = params.get("code", "")

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        msg = b"<h2>Authorization complete. You can close this tab.</h2>"
        self.wfile.write(msg)

    def log_message(self, *args: object) -> None:  # suppress server logs
        pass


def main() -> None:
    if not _CLIENT_ID or not _CLIENT_SECRET:
        print("ERROR: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env")
        sys.exit(1)

    # Build Google OAuth2 authorization URL
    auth_params = urllib.parse.urlencode({
        "client_id":     _CLIENT_ID,
        "redirect_uri":  _REDIRECT_URI,
        "response_type": "code",
        "scope":         _SCOPES,
        "access_type":   "offline",
        "prompt":        "consent",   # force refresh_token to be returned
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{auth_params}"

    print("\n=== YouTube OAuth2 Authorization ===")
    print("Opening browser for Google sign-in...")
    print(f"If it doesn't open automatically:\n  {auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for the redirect callback on localhost:8080
    server = HTTPServer(("localhost", 8080), _CallbackHandler)
    server.handle_request()   # blocks until one request received

    if not _auth_code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    # Exchange auth code for tokens
    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code":          _auth_code,
            "client_id":     _CLIENT_ID,
            "client_secret": _CLIENT_SECRET,
            "redirect_uri":  _REDIRECT_URI,
            "grant_type":    "authorization_code",
        },
        timeout=30.0,
        verify=False,   # corporate SSL proxy uses self-signed cert
    )

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed {resp.status_code}: {resp.text}")
        sys.exit(1)

    tokens = resp.json()
    refresh_token = tokens.get("refresh_token", "")

    if not refresh_token:
        print("ERROR: No refresh_token in response. Did you revoke access previously?")
        print("  Visit https://myaccount.google.com/permissions and remove AI Squadron,")
        print("  then re-run this script.")
        sys.exit(1)

    print("\n=== SUCCESS ===")
    print("Add this line to your .env file:\n")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}\n")


if __name__ == "__main__":
    main()
