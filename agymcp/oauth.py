"""OAuth 2.1 + PKCE + Dynamic Client Registration (RFC 7591/8414/8707/9728) for MCP servers."""

from __future__ import annotations

import base64
import hashlib
import html
import http.server
import json
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from agymcp.core import CLAUDE_CODE_USER_AGENT, normalize_url

TOKENS_PATH = Path.home() / ".config" / "agymcp" / "tokens.json"


@dataclass(frozen=True)
class OAuthMetadata:
    """Discovered OAuth 2.1 endpoints for a remote MCP server."""

    resource: str
    resource_name: str
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: str
    scopes_supported: tuple[str, ...] = ()


@dataclass(frozen=True)
class OAuthTokenResult:
    """OAuth access/refresh tokens obtained from the authorization server."""

    access_token: str
    token_type: str = "Bearer"
    refresh_token: str = ""
    expires_at: float | None = None
    scope: str = ""
    client_id: str = ""
    client_secret: str = ""
    token_endpoint: str = ""
    resource: str = ""


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE (code_verifier, S256 code_challenge) pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _http_get_json(url: str, timeout: float = 6.0) -> dict[str, Any] | None:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": CLAUDE_CODE_USER_AGENT,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if 200 <= getattr(resp, "status", 200) < 300:
                parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
                if isinstance(parsed, dict):
                    return parsed
    except Exception:  # noqa: BLE001
        return None
    return None


def _well_known_candidates(base_url: str, suffix: str) -> list[str]:
    """Build RFC 8414 / RFC 9728 path-inserted and root well-known URLs."""
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path.rstrip("/")
    candidates: list[str] = []
    if path:
        candidates.append(f"{origin}/.well-known/{suffix}{path}")
    candidates.append(f"{origin}/.well-known/{suffix}")
    return candidates


def discover_oauth_metadata(
    mcp_url: str,
    www_authenticate: str = "",
    timeout: float = 6.0,
) -> OAuthMetadata:
    """Discover OAuth 2.1 authorization, token, and dynamic registration endpoints."""
    norm_url = normalize_url(mcp_url)
    parsed = urlparse(norm_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    # 1. Protected resource metadata (RFC 9728)
    prm_candidates: list[str] = []
    if www_authenticate:
        match = re.search(r'resource_metadata="([^"]+)"', www_authenticate)
        if match:
            prm_candidates.append(urljoin(origin, match.group(1)))
    prm_candidates.extend(_well_known_candidates(norm_url, "oauth-protected-resource"))

    resource = norm_url
    resource_name = ""
    auth_server_urls: list[str] = []

    seen: set[str] = set()
    for candidate in prm_candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        meta = _http_get_json(candidate, timeout=timeout)
        if meta:
            if isinstance(meta.get("resource"), str) and meta["resource"].strip():
                resource = meta["resource"].strip()
            if isinstance(meta.get("resource_name"), str):
                resource_name = meta["resource_name"].strip()
            servers = meta.get("authorization_servers")
            if isinstance(servers, list):
                auth_server_urls.extend(str(s).strip() for s in servers if str(s).strip())
            break

    if not auth_server_urls:
        auth_server_urls = [norm_url, origin]

    # 2. Authorization server metadata (RFC 8414 / OpenID Connect Discovery)
    asm_candidates: list[str] = []
    for auth_srv in auth_server_urls:
        asm_candidates.extend(_well_known_candidates(auth_srv, "oauth-authorization-server"))
        asm_candidates.extend(_well_known_candidates(auth_srv, "openid-configuration"))

    seen_asm: set[str] = set()
    for candidate in asm_candidates:
        if candidate in seen_asm:
            continue
        seen_asm.add(candidate)
        asm = _http_get_json(candidate, timeout=timeout)
        if asm and asm.get("authorization_endpoint") and asm.get("token_endpoint"):
            scopes = asm.get("scopes_supported")
            scopes_tuple = (
                tuple(str(s) for s in scopes if str(s).strip())
                if isinstance(scopes, list)
                else ()
            )
            return OAuthMetadata(
                resource=resource,
                resource_name=resource_name,
                issuer=str(asm.get("issuer") or auth_server_urls[0]),
                authorization_endpoint=str(asm["authorization_endpoint"]),
                token_endpoint=str(asm["token_endpoint"]),
                registration_endpoint=str(asm.get("registration_endpoint") or ""),
                scopes_supported=scopes_tuple,
            )

    raise RuntimeError(
        f"Impossibile scoprire i metadati OAuth 2.1 per {norm_url}."
    )


def register_dynamic_client(
    metadata: OAuthMetadata,
    redirect_uri: str,
    timeout: float = 8.0,
) -> tuple[str, str]:
    """Perform RFC 7591 OAuth Dynamic Client Registration."""
    if not metadata.registration_endpoint:
        raise RuntimeError(
            "Questo server OAuth non espone un endpoint di registrazione dinamica (RFC 7591)."
        )

    payload = {
        "client_name": "agymcp (claude-code)",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    }
    req = urllib.request.Request(
        metadata.registration_endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": CLAUDE_CODE_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        exc.close()
        raise RuntimeError(
            f"Registrazione client OAuth fallita (HTTP {exc.code}): {detail}"
        ) from exc

    client_id = str(data.get("client_id") or "").strip()
    client_secret = str(data.get("client_secret") or "").strip()
    if not client_id:
        raise RuntimeError("Il server OAuth non ha restituito un client_id valido.")
    return client_id, client_secret


def _exchange_token(
    token_endpoint: str,
    form_fields: dict[str, str],
    timeout: float = 10.0,
) -> dict[str, Any]:
    body = urlencode(form_fields).encode("utf-8")
    req = urllib.request.Request(
        token_endpoint,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": CLAUDE_CODE_USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            if not isinstance(data, dict):
                raise RuntimeError("Risposta token OAuth non valida.")
            return data
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        exc.close()
        raise RuntimeError(f"Scambio token OAuth fallito (HTTP {exc.code}): {detail}") from exc


def load_token_store(tokens_path: Path = TOKENS_PATH) -> dict[str, dict[str, Any]]:
    """Load persisted OAuth refresh metadata from disk."""
    if not tokens_path.exists():
        return {}
    try:
        data = json.loads(tokens_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:  # noqa: BLE001
        pass
    return {}


def save_token_record(
    server_name: str,
    token: OAuthTokenResult,
    tokens_path: Path = TOKENS_PATH,
) -> None:
    """Persist refresh_token and client metadata with strict 0600 permissions."""
    store = load_token_store(tokens_path)
    store[server_name] = {
        "refresh_token": token.refresh_token,
        "client_id": token.client_id,
        "client_secret": token.client_secret,
        "token_endpoint": token.token_endpoint,
        "resource": token.resource,
        "expires_at": token.expires_at,
        "scope": token.scope,
    }
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    tokens_path.write_text(
        json.dumps(store, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    try:
        os.chmod(tokens_path, 0o600)
    except OSError:
        pass


def refresh_oauth_token(
    server_name: str,
    tokens_path: Path = TOKENS_PATH,
    timeout: float = 10.0,
) -> OAuthTokenResult | None:
    """Attempt a silent OAuth token refresh using the saved refresh_token."""
    store = load_token_store(tokens_path)
    rec = store.get(server_name)
    if not isinstance(rec, dict):
        return None
    refresh_token = str(rec.get("refresh_token") or "").strip()
    token_endpoint = str(rec.get("token_endpoint") or "").strip()
    client_id = str(rec.get("client_id") or "").strip()
    if not refresh_token or not token_endpoint or not client_id:
        return None

    fields: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    client_secret = str(rec.get("client_secret") or "").strip()
    if client_secret:
        fields["client_secret"] = client_secret
    resource = str(rec.get("resource") or "").strip()
    if resource:
        fields["resource"] = resource

    try:
        data = _exchange_token(token_endpoint, fields, timeout=timeout)
    except Exception:  # noqa: BLE001
        return None

    access_token = str(data.get("access_token") or "").strip()
    if not access_token:
        return None

    expires_in = data.get("expires_in")
    expires_at = (
        time.time() + float(expires_in)
        if isinstance(expires_in, (int, float))
        else None
    )
    new_refresh = str(data.get("refresh_token") or refresh_token).strip()
    result = OAuthTokenResult(
        access_token=access_token,
        token_type=str(data.get("token_type") or "Bearer"),
        refresh_token=new_refresh,
        expires_at=expires_at,
        scope=str(data.get("scope") or rec.get("scope") or ""),
        client_id=client_id,
        client_secret=client_secret,
        token_endpoint=token_endpoint,
        resource=resource,
    )
    save_token_record(server_name, result, tokens_path=tokens_path)
    return result


def _render_callback_html(title: str, subtitle: str, ok: bool) -> bytes:
    dot_color = "#22C55E" if ok else "#EF4444"
    page = f"""<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<title>{html.escape(title)} · agymcp</title>
<style>
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #09090B; color: #EDEDEF; font-family: system-ui, -apple-system, sans-serif;
  }}
  .card {{
    background: #121214; border: 1px solid #222226; border-radius: 10px;
    padding: 28px 32px; max-width: 440px; width: 90%;
  }}
  .row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: {dot_color}; }}
  h1 {{ font-size: 16px; margin: 0; font-weight: 600; letter-spacing: -0.02em; }}
  p {{ color: #8E8E93; font-size: 13px; margin: 0; line-height: 1.5; }}
</style>
</head>
<body>
  <div class="card">
    <div class="row"><span class="dot"></span><h1>{html.escape(title)}</h1></div>
    <p>{html.escape(subtitle)}</p>
  </div>
</body>
</html>"""
    return page.encode("utf-8")


def run_oauth_login(
    mcp_url: str,
    server_name: str,
    open_browser: bool = True,
    timeout: float = 180.0,
    tokens_path: Path = TOKENS_PATH,
    status_callback: Callable[[str], None] | None = None,
) -> OAuthTokenResult:
    """Run the full OAuth 2.1 + PKCE + Dynamic Client Registration browser flow."""
    if status_callback:
        status_callback("Scoperta metadati OAuth 2.1 in corso...")
    metadata = discover_oauth_metadata(mcp_url)

    callback_result: dict[str, str] = {}
    callback_event = threading.Event()

    class _CallbackHandler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

        def do_GET(self) -> None:  # noqa: N802
            parsed_cb = urlparse(self.path)
            if parsed_cb.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            params = parse_qs(parsed_cb.query)
            if "error" in params:
                err = params["error"][0]
                desc = params.get("error_description", [""])[0]
                callback_result["error"] = f"{err}: {desc}".strip(": ")
                body = _render_callback_html(
                    "Autenticazione annullata",
                    callback_result["error"],
                    ok=False,
                )
            else:
                callback_result["code"] = params.get("code", [""])[0]
                callback_result["state"] = params.get("state", [""])[0]
                body = _render_callback_html(
                    "Autenticazione completata",
                    "Puoi chiudere questa scheda e tornare su agymcp.",
                    ok=True,
                )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            callback_event.set()

    httpd = http.server.HTTPServer(("127.0.0.1", 0), _CallbackHandler)
    port = httpd.server_address[1]
    redirect_uri = f"http://127.0.0.1:{port}/callback"

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    try:
        if status_callback:
            status_callback("Registrazione client OAuth (PKCE)...")
        client_id, client_secret = register_dynamic_client(metadata, redirect_uri)

        code_verifier, code_challenge = generate_pkce_pair()
        state = secrets.token_urlsafe(24)

        auth_params: dict[str, str] = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "resource": metadata.resource,
        }
        if metadata.scopes_supported:
            auth_params["scope"] = " ".join(metadata.scopes_supported)

        sep = "&" if "?" in metadata.authorization_endpoint else "?"
        auth_url = f"{metadata.authorization_endpoint}{sep}{urlencode(auth_params)}"

        if status_callback:
            status_callback("Completa il login nel browser...")
        if open_browser:
            webbrowser.open(auth_url)

        if not callback_event.wait(timeout=timeout):
            raise TimeoutError("Timeout in attesa del login OAuth nel browser.")

        if "error" in callback_result:
            raise RuntimeError(f"Errore OAuth: {callback_result['error']}")

        if callback_result.get("state") != state:
            raise RuntimeError("Verifica state OAuth fallita (possibile CSRF).")

        code = callback_result.get("code", "").strip()
        if not code:
            raise RuntimeError("Codice di autorizzazione OAuth mancante.")

        if status_callback:
            status_callback("Scambio codice per access token...")

        token_fields: dict[str, str] = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": code_verifier,
            "resource": metadata.resource,
        }
        if client_secret:
            token_fields["client_secret"] = client_secret

        token_data = _exchange_token(metadata.token_endpoint, token_fields)
        access_token = str(token_data.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("Il server OAuth non ha restituito un access_token.")

        expires_in = token_data.get("expires_in")
        expires_at = (
            time.time() + float(expires_in)
            if isinstance(expires_in, (int, float))
            else None
        )
        result = OAuthTokenResult(
            access_token=access_token,
            token_type=str(token_data.get("token_type") or "Bearer"),
            refresh_token=str(token_data.get("refresh_token") or "").strip(),
            expires_at=expires_at,
            scope=str(token_data.get("scope") or ""),
            client_id=client_id,
            client_secret=client_secret,
            token_endpoint=metadata.token_endpoint,
            resource=metadata.resource,
        )
        if result.refresh_token:
            save_token_record(server_name, result, tokens_path=tokens_path)
        return result
    finally:
        httpd.shutdown()
        httpd.server_close()
