"""Core configuration and Claude Code-compatible MCP handshake engine for agymcp."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

DEFAULT_CONFIG_PATH = Path.home() / ".gemini" / "config" / "mcp_config.json"

MCP_PROTOCOL_VERSION = "2025-03-26"
CLAUDE_CODE_USER_AGENT = "claude-code/2.1.0"
CLAUDE_CODE_CLIENT_INFO = {
    "name": "claude-code",
    "version": "2.1.0",
}

_GENERIC_SUBDOMAINS = {"api", "mcp", "www", "server", "connect", "app"}
_COMMON_TLDS = {
    "com",
    "org",
    "net",
    "io",
    "dev",
    "ai",
    "co",
    "app",
    "gg",
    "me",
    "it",
    "uk",
    "eu",
    "us",
    "ca",
    "de",
    "fr",
    "es",
    "nl",
    "cloud",
    "tech",
    "xyz",
    "sh",
    "so",
    "to",
    "ly",
}
_HOSTED_SUFFIXES = (
    ("googleapis", "com"),
    ("run", "app"),
    ("workers", "dev"),
    ("pages", "dev"),
    ("vercel", "app"),
    ("netlify", "app"),
    ("herokuapp", "com"),
    ("railway", "app"),
    ("fly", "dev"),
)


def normalize_url(url: str) -> str:
    """Validate and normalize an HTTP/HTTPS MCP endpoint URL."""
    cleaned = url.strip()
    if not cleaned:
        raise ValueError("L'URL non può essere vuoto.")
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"URL non valido: {url!r}")
    return cleaned


def sanitize_server_name(raw_name: str) -> str:
    """Sanitize a server identifier into a clean lowercase slug."""
    candidate = re.sub(r"[^a-z0-9_-]+", "-", raw_name.strip().lower()).strip("-_")
    return candidate


def infer_server_name(url: str) -> str:
    """Infer a clean Antigravity server identifier from an MCP URL."""
    cleaned = url.strip()
    if not cleaned:
        return ""
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    hostname = (parsed.hostname or "").lower().strip(".")
    if not hostname:
        return ""

    parts = [p for p in hostname.split(".") if p]
    if not parts:
        return ""

    if all(p.isdigit() for p in parts):
        return "-".join(parts)

    matched_hosted = False
    for suffix in _HOSTED_SUFFIXES:
        n = len(suffix)
        if len(parts) > n and tuple(parts[-n:]) == suffix:
            parts = parts[:-n]
            matched_hosted = True
            break

    if not matched_hosted and len(parts) > 1:
        last = parts[-1]
        if last in _COMMON_TLDS or (len(last) == 2 and last.isalpha()):
            parts = parts[:-1]
            if len(parts) > 1 and parts[-1] in {"co", "com", "org", "net"}:
                parts = parts[:-1]

    while len(parts) > 1 and parts[0] in _GENERIC_SUBDOMAINS:
        parts = parts[1:]

    candidate = sanitize_server_name("-".join(parts))
    return candidate or "mcp-server"


def is_sse_url(url: str) -> bool:
    """Return True if the URL path appears to target a legacy /sse endpoint."""
    cleaned = url.strip()
    if not cleaned:
        return False
    if "://" not in cleaned:
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    return parsed.path.rstrip("/").lower().endswith("/sse")


def parse_headers_text(raw_text: str) -> dict[str, str]:
    """Parse multiline 'Key: Value' header pairs into a dictionary."""
    headers: dict[str, str] = {}
    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(
                f"Header non valido alla riga {line_no}: usa il formato 'Chiave: Valore'."
            )
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"Nome header vuoto alla riga {line_no}.")
        headers[key] = value
    return headers


def parse_env_text(raw_text: str) -> dict[str, str]:
    """Parse multiline 'KEY=VALUE' pairs into an environment dictionary."""
    env: dict[str, str] = {}
    for line_no, raw_line in enumerate(raw_text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(
                f"Variabile ambiente non valida alla riga {line_no}: usa 'CHIAVE=VALORE'."
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Nome variabile vuoto alla riga {line_no}.")
        env[key] = value
    return env


def _parse_mcp_jsonrpc_body(body: bytes, content_type: str = "") -> dict[str, Any] | None:
    """Parse a JSON-RPC payload returned either as application/json or text/event-stream."""
    text = body.decode("utf-8", errors="replace").strip()
    if not text:
        return None

    # Standard JSON response
    if "text/event-stream" not in content_type.lower():
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and ("result" in item or "error" in item):
                        return item
        except json.JSONDecodeError:
            pass

    # Streamable HTTP SSE frame(s): extract JSON from `data:` lines
    data_chunks: list[str] = []
    for line in text.splitlines():
        if line.startswith("data:"):
            payload_str = line[5:].strip()
            if payload_str and payload_str != "[DONE]":
                data_chunks.append(payload_str)
                try:
                    parsed = json.loads(payload_str)
                    if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
                        return parsed
                except json.JSONDecodeError:
                    continue

    if data_chunks:
        try:
            parsed = json.loads("\n".join(data_chunks))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return None


def _discover_oauth_support(
    url: str,
    www_authenticate: str,
    timeout: float = 4.0,
) -> tuple[bool, str]:
    """Check WWW-Authenticate and RFC 9728/8414 well-known endpoints for OAuth support."""
    candidates: list[str] = []
    if www_authenticate:
        match = re.search(r'resource_metadata="([^"]+)"', www_authenticate)
        if match:
            candidates.append(match.group(1))

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    path_suffix = parsed.path.rstrip("/")
    if path_suffix:
        candidates.append(f"{origin}/.well-known/oauth-protected-resource{path_suffix}")
    candidates.append(f"{origin}/.well-known/oauth-protected-resource")
    candidates.append(f"{origin}/.well-known/oauth-authorization-server")

    seen: set[str] = set()
    for candidate in candidates:
        full_url = urljoin(origin, candidate)
        if full_url in seen:
            continue
        seen.add(full_url)
        req = urllib.request.Request(
            full_url,
            headers={
                "Accept": "application/json",
                "User-Agent": CLAUDE_CODE_USER_AGENT,
            },
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if 200 <= getattr(resp, "status", 200) < 300:
                    meta = json.loads(resp.read().decode("utf-8", errors="replace"))
                    if isinstance(meta, dict) and (
                        "authorization_servers" in meta
                        or "authorization_endpoint" in meta
                        or "token_endpoint" in meta
                        or "resource" in meta
                    ):
                        auth_servers = meta.get("authorization_servers")
                        issuer = (
                            str(auth_servers[0])
                            if isinstance(auth_servers, list) and auth_servers
                            else str(meta.get("issuer") or meta.get("authorization_endpoint") or "")
                        )
                        return True, issuer
        except Exception:  # noqa: BLE001
            continue

    if www_authenticate and "bearer" in www_authenticate.lower() and "resource_metadata" in www_authenticate.lower():
        return True, ""
    return False, ""


def _post_jsonrpc(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> tuple[int, dict[str, str], bytes]:
    """Send a JSON-RPC POST request impersonating Claude Code."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        resp_headers = {k.lower(): v for k, v in resp.headers.items()}
        body = resp.read(256 * 1024)
        return status, resp_headers, body


def probe_mcp_url(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: float = 6.0,
) -> dict[str, Any]:
    """Perform a real MCP Streamable HTTP handshake impersonating Claude Code.

    Sends JSON-RPC `initialize` (with Claude Code clientInfo & User-Agent),
    follows up with `notifications/initialized` + `tools/list` when authorized,
    and checks OAuth discovery metadata on HTTP 401/403.
    """
    base_result: dict[str, Any] = {
        "reachable": False,
        "status_code": None,
        "transport": "unknown",
        "needs_auth": False,
        "auth_type": "none",
        "is_legacy_sse": False,
        "server_name": "",
        "server_version": "",
        "suggested_name": "",
        "tools_count": None,
        "tools_preview": [],
        "message": "",
    }

    try:
        norm_url = normalize_url(url)
    except ValueError as exc:
        base_result["message"] = str(exc)
        return base_result

    legacy_sse = is_sse_url(norm_url)
    base_result["is_legacy_sse"] = legacy_sse

    req_headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": CLAUDE_CODE_USER_AGENT,
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
    }
    if headers:
        req_headers.update(headers)

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {},
            },
            "clientInfo": CLAUDE_CODE_CLIENT_INFO,
        },
    }

    try:
        status, resp_headers, body = _post_jsonrpc(
            norm_url, init_payload, req_headers, timeout=timeout
        )
        base_result["reachable"] = True
        base_result["status_code"] = status
        base_result["transport"] = "legacy-sse" if legacy_sse else "streamable-http"

        rpc = _parse_mcp_jsonrpc_body(body, resp_headers.get("content-type", ""))
        result_obj = rpc.get("result") if isinstance(rpc, dict) else None
        if isinstance(result_obj, dict):
            srv_info = result_obj.get("serverInfo")
            if isinstance(srv_info, dict):
                srv_name = str(srv_info.get("name") or "").strip()
                srv_ver = str(srv_info.get("version") or "").strip()
                base_result["server_name"] = srv_name
                base_result["server_version"] = srv_ver
                base_result["suggested_name"] = sanitize_server_name(srv_name)

            # Follow-up: notifications/initialized + tools/list
            session_id = resp_headers.get("mcp-session-id")
            followup_headers = dict(req_headers)
            if session_id:
                followup_headers["Mcp-Session-Id"] = session_id

            try:
                _post_jsonrpc(
                    norm_url,
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    followup_headers,
                    timeout=min(timeout, 3.0),
                )
            except Exception:  # noqa: BLE001
                pass

            try:
                _, t_headers, t_body = _post_jsonrpc(
                    norm_url,
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
                    followup_headers,
                    timeout=min(timeout, 4.0),
                )
                t_rpc = _parse_mcp_jsonrpc_body(t_body, t_headers.get("content-type", ""))
                t_res = t_rpc.get("result") if isinstance(t_rpc, dict) else None
                if isinstance(t_res, dict) and isinstance(t_res.get("tools"), list):
                    tools_list = t_res["tools"]
                    base_result["tools_count"] = len(tools_list)
                    base_result["tools_preview"] = [
                        str(t.get("name"))
                        for t in tools_list[:5]
                        if isinstance(t, dict) and t.get("name")
                    ]
            except Exception:  # noqa: BLE001
                pass

        parts: list[str] = []
        if base_result["server_name"]:
            label = base_result["server_name"]
            if base_result["server_version"]:
                label += f" v{base_result['server_version']}"
            parts.append(label)
        else:
            parts.append(f"MCP attivo (HTTP {status})")

        parts.append("streamable-http")
        if base_result["tools_count"] is not None:
            parts.append(f"{base_result['tools_count']} tools")
        base_result["message"] = " · ".join(parts)
        return base_result

    except urllib.error.HTTPError as exc:
        code = exc.code
        base_result["status_code"] = code
        www_auth = exc.headers.get("WWW-Authenticate", "") if exc.headers else ""
        exc.close()

        if code in (401, 403):
            base_result["reachable"] = True
            base_result["needs_auth"] = True
            base_result["transport"] = "legacy-sse" if legacy_sse else "streamable-http"
            is_oauth, _issuer = _discover_oauth_support(
                norm_url, www_auth, timeout=min(timeout, 4.0)
            )
            if is_oauth:
                base_result["auth_type"] = "oauth"
                base_result["message"] = (
                    f"OAuth rilevato (HTTP {code}) · Antigravity gestirà il login automaticamente"
                )
            else:
                base_result["auth_type"] = "token"
                base_result["message"] = (
                    f"Autenticazione richiesta (HTTP {code}) · inserisci Bearer Token o API Key"
                )
            return base_result

        if code == 405 and legacy_sse:
            base_result["reachable"] = True
            base_result["transport"] = "legacy-sse"
            base_result["is_legacy_sse"] = True
            base_result["message"] = (
                "Endpoint legacy SSE rilevato · attiva il bridge npx mcp-remote"
            )
            return base_result

        if code in (400, 405, 406, 415, 422):
            # Some servers expect GET /sse for legacy SSE; check if path or response hints SSE
            base_result["reachable"] = True
            base_result["transport"] = "legacy-sse" if legacy_sse else "streamable-http"
            base_result["message"] = f"Endpoint raggiungibile (HTTP {code})"
            return base_result

        if code == 404:
            base_result["reachable"] = False
            base_result["message"] = "Endpoint non trovato (HTTP 404) · verifica il percorso"
            return base_result

        base_result["reachable"] = True
        base_result["message"] = f"Risposta server HTTP {code}"
        return base_result

    except Exception as exc:  # noqa: BLE001
        base_result["reachable"] = False
        base_result["message"] = f"Connessione fallita · {exc}"
        return base_result


class MCPConfigManager:
    """Safely reads, updates, backs up, and writes Antigravity's mcp_config.json."""

    def __init__(self, config_path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = Path(config_path).expanduser()

    @property
    def backup_path(self) -> Path:
        """Return the backup file path paired with config_path."""
        return self.config_path.with_name(f"{self.config_path.name}.bak")

    def load_config(self) -> dict[str, Any]:
        """Load the full configuration JSON, ensuring a valid 'mcpServers' map."""
        if not self.config_path.exists():
            return {"mcpServers": {}}
        raw = self.config_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {"mcpServers": {}}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Il file mcp_config.json deve contenere un oggetto JSON.")
        servers = data.get("mcpServers")
        if servers is None:
            data["mcpServers"] = {}
        elif not isinstance(servers, dict):
            raise ValueError("La chiave 'mcpServers' deve essere un oggetto JSON.")
        return data

    def load_raw_text(self) -> str:
        """Return formatted JSON text for display in the raw editor."""
        if self.config_path.exists():
            return self.config_path.read_text(encoding="utf-8")
        return json.dumps({"mcpServers": {}}, indent=2) + "\n"

    def save_config(self, data: dict[str, Any]) -> None:
        """Create a .bak backup and atomically write the updated JSON configuration."""
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
            raise ValueError("La configurazione deve contenere un oggetto 'mcpServers'.")

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if self.config_path.exists():
            shutil.copy2(self.config_path, self.backup_path)

        serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{self.config_path.name}.",
            suffix=".tmp",
            dir=str(self.config_path.parent),
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.config_path)
        except Exception:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            raise

    def save_raw_text(self, raw_text: str) -> dict[str, Any]:
        """Parse, validate, and save raw JSON configuration text."""
        data = json.loads(raw_text)
        if not isinstance(data, dict):
            raise ValueError("Il JSON principale deve essere un oggetto.")
        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            raise ValueError("Il JSON deve contenere l'oggetto 'mcpServers'.")
        self.save_config(data)
        return data

    def restore_backup(self) -> bool:
        """Restore configuration from .bak if available and valid JSON."""
        if not self.backup_path.exists():
            return False
        raw = self.backup_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers"), dict):
            raise ValueError("Il file di backup non contiene una configurazione valida.")
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.backup_path, self.config_path)
        return True

    def get_servers(self) -> dict[str, dict[str, Any]]:
        """Return a deep copy of configured servers."""
        return copy.deepcopy(self.load_config()["mcpServers"])

    @staticmethod
    def classify_server(entry: dict[str, Any]) -> str:
        """Classify a server entry as 'remote', 'bridge', or 'stdio'."""
        if "serverUrl" in entry or "url" in entry:
            return "remote"
        args = [str(a) for a in entry.get("args", [])]
        if entry.get("command") == "npx" and any("mcp-remote" in arg for arg in args):
            return "bridge"
        return "stdio"

    @staticmethod
    def get_server_endpoint(entry: dict[str, Any]) -> str:
        """Return a concise human-readable summary of a server's URL or command."""
        kind = MCPConfigManager.classify_server(entry)
        if kind == "remote":
            return str(entry.get("serverUrl") or entry.get("url") or "")
        if kind == "bridge":
            args = [str(a) for a in entry.get("args", [])]
            for idx, arg in enumerate(args):
                if "mcp-remote" in arg and idx + 1 < len(args):
                    return args[idx + 1]
            return f"{entry.get('command', '')} {' '.join(args)}".strip()
        cmd = str(entry.get("command", ""))
        args = " ".join(str(a) for a in entry.get("args", []))
        return f"{cmd} {args}".strip()

    @staticmethod
    def summarize_secrets_count(entry: dict[str, Any]) -> str:
        """Return a safe count tag for headers/env without exposing secret values."""
        notes: list[str] = []
        headers = entry.get("headers")
        if isinstance(headers, dict) and headers:
            notes.append(f"{len(headers)} header")
        env = entry.get("env")
        if isinstance(env, dict) and env:
            notes.append(f"{len(env)} env")
        args = [str(a) for a in entry.get("args", [])]
        header_flags = args.count("--header")
        if header_flags:
            notes.append(f"{header_flags} header")
        return f" · {', '.join(notes)}" if notes else ""

    def add_remote_server(
        self,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        use_bridge: bool = False,
        disabled: bool = False,
    ) -> dict[str, Any]:
        """Add or update a remote HTTP (or mcp-remote SSE bridge) MCP server."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Il nome del server non può essere vuoto.")
        norm_url = normalize_url(url)
        clean_headers = {
            str(k).strip(): str(v).strip()
            for k, v in (headers or {}).items()
            if str(k).strip() and str(v).strip()
        }

        if use_bridge:
            args = ["-y", "mcp-remote", norm_url]
            for key, value in clean_headers.items():
                args.extend(["--header", f"{key}: {value}"])
            entry: dict[str, Any] = {
                "command": "npx",
                "args": args,
                "disabled": bool(disabled),
            }
        else:
            entry = {
                "serverUrl": norm_url,
                "disabled": bool(disabled),
            }
            if clean_headers:
                entry["headers"] = clean_headers

        data = self.load_config()
        data["mcpServers"][clean_name] = entry
        self.save_config(data)
        return entry

    def add_stdio_server(
        self,
        name: str,
        command: str,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        disabled: bool = False,
    ) -> dict[str, Any]:
        """Add or update a local Stdio MCP server."""
        clean_name = name.strip()
        clean_cmd = command.strip()
        if not clean_name:
            raise ValueError("Il nome del server non può essere vuoto.")
        if not clean_cmd:
            raise ValueError("Il comando eseguibile non può essere vuoto.")

        entry: dict[str, Any] = {
            "command": clean_cmd,
            "args": [str(a) for a in (args or []) if str(a) != ""],
            "disabled": bool(disabled),
        }
        clean_env = {
            str(k).strip(): str(v)
            for k, v in (env or {}).items()
            if str(k).strip()
        }
        if clean_env:
            entry["env"] = clean_env

        data = self.load_config()
        data["mcpServers"][clean_name] = entry
        self.save_config(data)
        return entry

    def set_server_entry(self, name: str, entry: dict[str, Any]) -> None:
        """Save an arbitrary validated server entry dict under the given name."""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Il nome del server non può essere vuoto.")
        if not isinstance(entry, dict):
            raise ValueError("La configurazione del server deve essere un oggetto JSON.")
        data = self.load_config()
        data["mcpServers"][clean_name] = entry
        self.save_config(data)

    def set_server_enabled(self, name: str, enabled: bool) -> None:
        """Enable or disable an existing MCP server entry."""
        data = self.load_config()
        if name not in data["mcpServers"]:
            raise KeyError(f"Server '{name}' non trovato.")
        data["mcpServers"][name]["disabled"] = not enabled
        self.save_config(data)

    def remove_server(self, name: str) -> bool:
        """Remove a server entry by name. Return True if removed."""
        data = self.load_config()
        if name not in data["mcpServers"]:
            return False
        del data["mcpServers"][name]
        self.save_config(data)
        return True
