"""End-to-end tests for OAuth 2.1 + PKCE + Dynamic Client Registration."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlparse

from agymcp.oauth import (
    discover_oauth_metadata,
    generate_pkce_pair,
    load_token_store,
    refresh_oauth_token,
    run_oauth_login,
)


class _MockOAuthServer(http.server.BaseHTTPRequestHandler):
    expected_challenge: str = ""
    issued_code: str = "auth-code-xyz"

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def _base(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        base = self._base()
        if self.path == "/.well-known/oauth-protected-resource/mcp":
            self._send_json(
                200,
                {
                    "resource": f"{base}/mcp",
                    "resource_name": "Mock MCP",
                    "authorization_servers": [f"{base}/mcp"],
                },
            )
            return
        if self.path == "/.well-known/oauth-authorization-server/mcp":
            self._send_json(
                200,
                {
                    "issuer": f"{base}/mcp",
                    "authorization_endpoint": f"{base}/oauth2/start",
                    "token_endpoint": f"{base}/oauth2/token",
                    "registration_endpoint": f"{base}/oauth2/register",
                    "code_challenge_methods_supported": ["S256"],
                },
            )
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")

        if self.path == "/oauth2/register":
            req_data = json.loads(raw)
            if not req_data.get("redirect_uris"):
                self._send_json(400, {"error": "invalid_client_metadata"})
                return
            self._send_json(
                201,
                {
                    "client_id": "dyn-client-123",
                    "token_endpoint_auth_method": "none",
                },
            )
            return

        if self.path == "/oauth2/token":
            params = {k: v[0] for k, v in parse_qs(raw).items()}
            grant = params.get("grant_type")
            if grant == "authorization_code":
                verifier = params.get("code_verifier", "")
                computed = (
                    base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
                    .rstrip(b"=")
                    .decode("ascii")
                )
                if computed != _MockOAuthServer.expected_challenge:
                    self._send_json(400, {"error": "invalid_grant"})
                    return
                self._send_json(
                    200,
                    {
                        "access_token": "tok-access-initial",
                        "refresh_token": "tok-refresh-1",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                )
                return

            if grant == "refresh_token" and params.get("refresh_token") == "tok-refresh-1":
                self._send_json(
                    200,
                    {
                        "access_token": "tok-access-refreshed",
                        "refresh_token": "tok-refresh-2",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                )
                return

            self._send_json(400, {"error": "unsupported_grant_type"})
            return

        self.send_response(404)
        self.end_headers()


class TestOAuthFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _MockOAuthServer)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_pkce_pair(self) -> None:
        verifier, challenge = generate_pkce_pair()
        self.assertGreaterEqual(len(verifier), 43)
        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        self.assertEqual(challenge, expected)

    def test_full_oauth_login_and_refresh(self) -> None:
        mcp_url = f"http://127.0.0.1:{self.port}/mcp"
        meta = discover_oauth_metadata(mcp_url)
        self.assertEqual(meta.resource_name, "Mock MCP")
        self.assertTrue(meta.registration_endpoint.endswith("/oauth2/register"))

        def fake_browser_open(auth_url: str) -> bool:
            parsed = urlparse(auth_url)
            q = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            _MockOAuthServer.expected_challenge = q["code_challenge"]
            cb_url = f"{q['redirect_uri']}?{urlencode({'code': _MockOAuthServer.issued_code, 'state': q['state']})}"

            def _hit_callback() -> None:
                with urllib.request.urlopen(cb_url, timeout=5) as resp:
                    self.assertEqual(resp.status, 200)

            threading.Thread(target=_hit_callback, daemon=True).start()
            return True

        with tempfile.TemporaryDirectory() as tmp:
            tokens_path = Path(tmp) / "tokens.json"
            with patch("agymcp.oauth.webbrowser.open", side_effect=fake_browser_open):
                tok = run_oauth_login(
                    mcp_url=mcp_url,
                    server_name="mock-mcp",
                    tokens_path=tokens_path,
                    timeout=10.0,
                )

            self.assertEqual(tok.access_token, "tok-access-initial")
            self.assertEqual(tok.refresh_token, "tok-refresh-1")
            self.assertEqual(os.stat(tokens_path).st_mode & 0o777, 0o600)
            self.assertIn("mock-mcp", load_token_store(tokens_path))

            # Silent refresh without browser
            refreshed = refresh_oauth_token("mock-mcp", tokens_path=tokens_path)
            self.assertIsNotNone(refreshed)
            assert refreshed is not None
            self.assertEqual(refreshed.access_token, "tok-access-refreshed")
            self.assertEqual(refreshed.refresh_token, "tok-refresh-2")


if __name__ == "__main__":
    unittest.main()
