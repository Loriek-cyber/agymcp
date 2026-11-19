"""Command-line interface and GUI launcher for agymcp."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from agymcp import __version__
from agymcp.core import (
    DEFAULT_CONFIG_PATH,
    MCPConfigManager,
    infer_server_name,
    is_sse_url,
    normalize_url,
    parse_headers_text,
    probe_mcp_url,
)
from agymcp.updater import apply_update, check_for_updates


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for agymcp."""
    parser = argparse.ArgumentParser(
        prog="agymcp",
        description=(
            "Installa e gestisci server MCP su Antigravity direttamente da link "
            "(es. agymcp https://api.streak.com/mcp) oppure apri la GUI desktop."
        ),
    )
    parser.add_argument(
        "url",
        nargs="?",
        help="Link del server MCP remoto da installare (es. https://api.streak.com/mcp)",
    )
    parser.add_argument(
        "-n",
        "--name",
        help="Nome identificativo del server in mcp_config.json (default: dedotto dal dominio)",
    )
    parser.add_argument(
        "-b",
        "--bearer",
        help="Bearer token da inviare come header 'Authorization: Bearer <token>'",
    )
    parser.add_argument(
        "-H",
        "--header",
        action="append",
        default=[],
        metavar="KEY: VALUE",
        help="Header HTTP personalizzato (ripetibile, es. -H 'X-Api-Key: secret')",
    )
    parser.add_argument(
        "--bridge",
        action="store_true",
        help="Configura via bridge Stdio 'npx -y mcp-remote' (per vecchi endpoint /sse)",
    )
    parser.add_argument(
        "--disabled",
        action="store_true",
        help="Installa il server in stato disattivato",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Apri l'interfaccia grafica desktop (precompilata se passi anche un URL)",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Percorso di mcp_config.json (default: {DEFAULT_CONFIG_PATH})",
    )

    actions = parser.add_argument_group("gestione server esistenti")
    actions.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="Elenca i server MCP configurati in Antigravity",
    )
    actions.add_argument(
        "--enable",
        metavar="NOME",
        help="Attiva un server MCP esistente",
    )
    actions.add_argument(
        "--disable",
        metavar="NOME",
        help="Disattiva un server MCP esistente",
    )
    actions.add_argument(
        "--remove",
        metavar="NOME",
        help="Rimuove un server MCP dalla configurazione",
    )
    actions.add_argument(
        "--test",
        metavar="URL",
        help="Testa la raggiungibilità HTTP di un endpoint MCP",
    )

    updates = parser.add_argument_group("aggiornamenti")
    updates.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    updates.add_argument(
        "--check-update",
        action="store_true",
        help="Controlla se è disponibile una nuova release di agymcp su GitHub",
    )
    updates.add_argument(
        "--update",
        action="store_true",
        help="Scarica e installa automaticamente l'ultima release di agymcp",
    )
    return parser


def _parse_cli_headers(args: argparse.Namespace) -> dict[str, str]:
    headers: dict[str, str] = {}
    if args.bearer:
        token = args.bearer.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        headers["Authorization"] = f"Bearer {token}"
    if args.header:
        headers.update(parse_headers_text("\n".join(args.header)))
    return headers


def _print_servers(manager: MCPConfigManager) -> int:
    servers = manager.get_servers()
    if not servers:
        print(f"Nessun server MCP configurato in {manager.config_path}")
        return 0

    print(f"Server MCP in {manager.config_path}:")
    for name, entry in sorted(servers.items()):
        status = "DISABLED" if entry.get("disabled", False) else "ENABLED "
        kind = MCPConfigManager.classify_server(entry).upper()
        endpoint = MCPConfigManager.get_server_endpoint(entry)
        secrets = MCPConfigManager.summarize_secrets_count(entry)
        print(f"  [{status}] {name:<22} {kind:<7} {endpoint}{secrets}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint supporting direct link install, management flags, and GUI launch."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    manager = MCPConfigManager(args.config)

    if args.gui or (
        not args.url
        and not args.list
        and not args.enable
        and not args.disable
        and not args.remove
        and not args.test
        and not args.check_update
        and not args.update
    ):
        from agymcp.gui import launch_gui

        return launch_gui(manager=manager, initial_url=args.url or "")

    try:
        if args.check_update:
            info = check_for_updates()
            if info.error:
                print(info.error, file=sys.stderr)
                return 1
            if info.update_available:
                print(
                    f"Nuova versione disponibile: v{info.latest_version} "
                    f"(attuale: v{info.current_version})"
                )
                if info.release_url:
                    print(f"Release: {info.release_url}")
                print("Esegui 'agymcp --update' per aggiornare automaticamente.")
            else:
                print(f"agymcp v{info.current_version} è già aggiornato.")
            return 0

        if args.update:
            info = check_for_updates()
            if info.error:
                print(info.error, file=sys.stderr)
                return 1
            result = apply_update(info)
            print(result.message)
            return 0 if result.success else 1

        if args.list:
            return _print_servers(manager)

        if args.enable:
            manager.set_server_enabled(args.enable, True)
            print(f"Server '{args.enable}' attivato in {manager.config_path}.")
            return 0

        if args.disable:
            manager.set_server_enabled(args.disable, False)
            print(f"Server '{args.disable}' disattivato in {manager.config_path}.")
            return 0

        if args.remove:
            if manager.remove_server(args.remove):
                print(f"Server '{args.remove}' rimosso da {manager.config_path}.")
                return 0
            print(f"Server '{args.remove}' non trovato.", file=sys.stderr)
            return 1

        if args.test:
            headers = _parse_cli_headers(args)
            result = probe_mcp_url(args.test, headers=headers)
            print(result["message"])
            return 0 if result["reachable"] else 1

        if args.url:
            norm_url = normalize_url(args.url)
            name = (args.name or "").strip() or infer_server_name(norm_url)
            headers = _parse_cli_headers(args)
            manager.add_remote_server(
                name=name,
                url=norm_url,
                headers=headers,
                use_bridge=bool(args.bridge),
                disabled=bool(args.disabled),
            )
            transport = "bridge npx mcp-remote" if args.bridge else "serverUrl HTTP"
            print(f"Installato '{name}' ({transport}) -> {norm_url}")
            print(f"Configurazione salvata in: {manager.config_path}")
            if not args.bridge and is_sse_url(norm_url):
                print(
                    "Nota: l'URL termina con /sse; se il server usa SSE legacy, "
                    "reinstallalo con --bridge."
                )
            return 0
    except (ValueError, KeyError) as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
