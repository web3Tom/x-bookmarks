from __future__ import annotations

import base64
import hashlib
import os
import secrets
import sys
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

AUTHORIZE_URL = "https://x.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
USERS_ME_URL = "https://api.x.com/2/users/me"
CALLBACK_PORT = 8000
REDIRECT_URI = f"http://127.0.0.1:{CALLBACK_PORT}/callback"
SCOPES = "tweet.read users.read bookmark.read offline.access"


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and S256 code_challenge."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _get_client_id() -> str:
    """Read CLIENT_ID from .env or environment."""
    client_id = os.environ.get("CLIENT_ID", "")
    if not client_id:
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("CLIENT_ID="):
                    client_id = line.split("=", 1)[1].strip()
                    break
    if not client_id:
        print("Error: CLIENT_ID not found. Set it in .env or environment.")
        sys.exit(1)
    return client_id


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to capture the OAuth callback."""

    auth_code: str | None = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this tab.</p>")
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<h1>Error: {error}</h1>".encode())

    def log_message(self, format, *args):
        pass


def _exchange_code(client_id: str, code: str, verifier: str) -> dict:
    """Exchange authorization code for tokens."""
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "code_verifier": verifier,
    }
    with httpx.Client() as client:
        resp = client.post(TOKEN_URL, data=data)
        resp.raise_for_status()
        return resp.json()


def _fetch_user_id(access_token: str) -> str:
    """Fetch the authenticated user's ID."""
    with httpx.Client() as client:
        resp = client.get(
            USERS_ME_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()["data"]["id"]


def _write_env(client_id: str, access_token: str, refresh_token: str, user_id: str) -> None:
    """Write credentials to .env file."""
    env_path = Path(".env")

    anthropic_key = ""
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                anthropic_key = line.split("=", 1)[1].strip()

    env_path.write_text(
        f"# X API OAuth 2.0 credentials\n"
        f"CLIENT_ID={client_id}\n"
        f"CLIENT_SECRET=\n"
        f"ACCESS_TOKEN={access_token}\n"
        f"REFRESH_TOKEN={refresh_token}\n"
        f"USER_ID={user_id}\n"
        f"\n"
        f"# Anthropic API\n"
        f"ANTHROPIC_API_KEY={anthropic_key}\n"
    )


def main() -> None:
    """Run the OAuth 2.0 PKCE authorization flow."""
    client_id = _get_client_id()
    verifier, challenge = _generate_pkce()

    state = secrets.token_urlsafe(32)

    auth_url = (
        f"{AUTHORIZE_URL}"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={SCOPES.replace(' ', '%20')}"
        f"&state={state}"
        f"&code_challenge={challenge}"
        f"&code_challenge_method=S256"
    )

    print("Opening browser for authorization...")
    print(f"If the browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print(f"Waiting for callback on port {CALLBACK_PORT}...")
    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), _CallbackHandler)
    server.handle_request()

    code = _CallbackHandler.auth_code
    if not code:
        print("Error: No authorization code received.")
        sys.exit(1)

    print("Exchanging code for tokens...")
    tokens = _exchange_code(client_id, code, verifier)

    access_token = tokens["access_token"]
    refresh_token = tokens.get("refresh_token", "")

    print("Fetching user ID...")
    user_id = _fetch_user_id(access_token)

    _write_env(client_id, access_token, refresh_token, user_id)

    print(f"\nSuccess! Credentials saved to .env")
    print(f"User ID: {user_id}")
    print(f"Access token expires in {tokens.get('expires_in', 'unknown')} seconds")
    print("\nRun 'x-bookmarks' to fetch and categorize your bookmarks.")


if __name__ == "__main__":
    main()
