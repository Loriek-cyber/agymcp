"""Native PyQt6 desktop interface for agymcp — Dark Mode Anti-AI Slop Design System."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from agymcp import __version__
from agymcp.core import (
    MCPConfigManager,
    infer_server_name,
    is_sse_url,
    normalize_url,
    parse_env_text,
    parse_headers_text,
    probe_mcp_url,
)
from agymcp.oauth import (
    OAuthTokenResult,
    refresh_oauth_token,
    run_oauth_login,
)
from agymcp.updater import (
    UpdateInfo,
    UpdateResult,
    apply_update,
    check_for_updates,
    load_settings,
    save_settings,
)

# Design System Palette (Pure Neutral Carbon Grays — Zero Blue-Slate, Zero Gradients)
COLOR_CANVAS = "#09090B"
COLOR_SURFACE = "#121214"
COLOR_ELEVATED = "#1A1A1E"
COLOR_BORDER = "#222226"
COLOR_DIVIDER = "#1F1F23"
COLOR_TEXT_PRIMARY = "#EDEDEF"
COLOR_TEXT_SECONDARY = "#8E8E93"
COLOR_TEXT_MUTED = "#52525B"
COLOR_DOT_OK = "#22C55E"
COLOR_DOT_WARN = "#F59E0B"
COLOR_DOT_ERR = "#EF4444"
COLOR_DOT_IDLE = "#52525B"

MONO_FONT_STACK = '"JetBrains Mono", "Geist Mono", "Fira Code", "DejaVu Sans Mono", monospace'

APP_STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {COLOR_CANVAS};
    color: {COLOR_TEXT_PRIMARY};
}}
QWidget {{
    color: {COLOR_TEXT_PRIMARY};
    font-size: 13px;
}}
QScrollArea {{
    background-color: {COLOR_CANVAS};
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background-color: {COLOR_CANVAS};
}}
QScrollBar:vertical {{
    background: {COLOR_CANVAS};
    width: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {COLOR_BORDER};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLOR_TEXT_MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QFrame#Card {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 10px;
}}
QFrame#UpdateBanner {{
    background-color: {COLOR_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
}}
QFrame#Divider {{
    background-color: {COLOR_DIVIDER};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QLineEdit, QPlainTextEdit, QComboBox {{
    background-color: {COLOR_CANVAS};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 8px 10px;
    selection-background-color: {COLOR_ELEVATED};
    selection-color: {COLOR_TEXT_PRIMARY};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border: 1px solid {COLOR_TEXT_MUTED};
}}
QLineEdit::placeholder, QPlainTextEdit::placeholder {{
    color: {COLOR_TEXT_MUTED};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    selection-background-color: {COLOR_BORDER};
    selection-color: {COLOR_TEXT_PRIMARY};
    outline: none;
}}

QPushButton#PrimaryButton {{
    background-color: {COLOR_TEXT_PRIMARY};
    color: {COLOR_CANVAS};
    border: none;
    border-radius: 6px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{
    background-color: #D4D4D8;
}}
QPushButton#PrimaryButton:pressed {{
    background-color: #A1A1AA;
}}
QPushButton#PrimaryButton:disabled {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_MUTED};
}}

QPushButton#GhostButton {{
    background-color: transparent;
    color: {COLOR_TEXT_SECONDARY};
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
}}
QPushButton#GhostButton:hover {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
}}
QPushButton#GhostButton:disabled {{
    color: {COLOR_TEXT_MUTED};
}}

QPushButton#TabButton {{
    background-color: transparent;
    color: {COLOR_TEXT_SECONDARY};
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    padding: 8px 4px;
    font-weight: 500;
}}
QPushButton#TabButton:hover {{
    color: {COLOR_TEXT_PRIMARY};
}}
QPushButton#TabButton[active="true"] {{
    color: {COLOR_TEXT_PRIMARY};
    border-bottom: 2px solid {COLOR_TEXT_PRIMARY};
}}

QPushButton#RowMenuButton {{
    background-color: transparent;
    color: {COLOR_TEXT_MUTED};
    border: none;
    border-radius: 5px;
    padding: 4px 8px;
    font-weight: 700;
    font-size: 14px;
}}
QPushButton#RowMenuButton:hover {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
}}

QFrame#ServerRow {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
}}
QFrame#ServerRow:hover {{
    background-color: {COLOR_ELEVATED};
}}

QCheckBox {{
    color: {COLOR_TEXT_SECONDARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid {COLOR_BORDER};
    background-color: {COLOR_CANVAS};
}}
QCheckBox::indicator:checked {{
    background-color: {COLOR_TEXT_SECONDARY};
    border: 3px solid {COLOR_CANVAS};
}}

QMenu {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 14px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: {COLOR_BORDER};
}}

QMessageBox {{
    background-color: {COLOR_SURFACE};
}}
QMessageBox QLabel {{
    color: {COLOR_TEXT_PRIMARY};
}}
QMessageBox QPushButton {{
    background-color: {COLOR_ELEVATED};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid {COLOR_BORDER};
    border-radius: 6px;
    padding: 6px 14px;
}}
QMessageBox QPushButton:hover {{
    background-color: {COLOR_BORDER};
}}
"""


def _make_divider() -> QFrame:
    div = QFrame()
    div.setObjectName("Divider")
    div.setFrameShape(QFrame.Shape.HLine)
    return div


def _make_status_dot(color: str = COLOR_DOT_IDLE) -> QFrame:
    dot = QFrame()
    dot.setFixedSize(6, 6)
    dot.setStyleSheet(f"background-color: {color}; border-radius: 3px; border: none;")
    return dot


def _apply_compact_heading(label: QLabel, point_size: int) -> None:
    font = QFont()
    font.setPointSize(point_size)
    font.setWeight(QFont.Weight.DemiBold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 98.0)
    label.setFont(font)
    label.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY};")


def _mono_font(point_size: int = 10) -> QFont:
    font = QFont("JetBrains Mono")
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(point_size)
    return font


class ProbeWorker(QThread):
    """Background thread running a Claude Code MCP handshake against a URL."""

    finished_probe = pyqtSignal(str, dict)

    def __init__(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.url = url
        self.headers = headers or {}

    def run(self) -> None:
        result = probe_mcp_url(self.url, headers=self.headers)
        self.finished_probe.emit(self.url, result)


class UpdateCheckWorker(QThread):
    """Background thread checking GitHub Releases for a newer agymcp version."""

    finished_check = pyqtSignal(object)

    def run(self) -> None:
        self.finished_check.emit(check_for_updates())


class UpdateInstallWorker(QThread):
    """Background thread downloading and installing an available agymcp release."""

    finished_install = pyqtSignal(object)

    def __init__(self, info: UpdateInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info

    def run(self) -> None:
        self.finished_install.emit(apply_update(self.info))


class OAuthLoginWorker(QThread):
    """Background thread executing OAuth 2.1 + PKCE login and post-auth MCP verification."""

    status_update = pyqtSignal(str)
    finished_oauth = pyqtSignal(str, str, object, str, dict)

    def __init__(
        self,
        server_name: str,
        url: str,
        try_refresh_first: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.server_name = server_name
        self.url = url
        self.try_refresh_first = try_refresh_first

    def run(self) -> None:
        try:
            token: OAuthTokenResult | None = None
            if self.try_refresh_first:
                self.status_update.emit("Rinnovo token OAuth in corso...")
                token = refresh_oauth_token(self.server_name)

            if token is None:
                token = run_oauth_login(
                    mcp_url=self.url,
                    server_name=self.server_name,
                    status_callback=self.status_update.emit,
                )

            self.status_update.emit("Verifica token con handshake MCP (claude-code)...")
            probe = probe_mcp_url(
                self.url,
                headers={"Authorization": f"Bearer {token.access_token}"},
            )
            self.finished_oauth.emit(self.server_name, self.url, token, "", probe)
        except Exception as exc:  # noqa: BLE001
            self.finished_oauth.emit(self.server_name, self.url, None, str(exc), {})


def _extract_bridge_details(entry: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Extract URL and --header pairs from an npx mcp-remote bridge entry."""
    args = [str(a) for a in entry.get("args", [])]
    url = ""
    headers: dict[str, str] = {}
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token == "--header" and idx + 1 < len(args):
            raw_hdr = args[idx + 1]
            if ":" in raw_hdr:
                k, v = raw_hdr.split(":", 1)
                headers[k.strip()] = v.strip()
            idx += 2
            continue
        if token.startswith("http://") or token.startswith("https://"):
            url = token
        idx += 1
    return url, headers


class ServerEditDialog(QDialog):
    """Elevated modal dialog for creating or editing a Remote, Bridge, or Stdio server."""

    MODE_REMOTE = 0
    MODE_BRIDGE = 1
    MODE_STDIO = 2

    def __init__(
        self,
        parent: QWidget | None = None,
        name: str = "",
        entry: dict[str, Any] | None = None,
        default_mode: int = MODE_REMOTE,
    ) -> None:
        super().__init__(parent)
        self._is_edit = bool(name)
        self.setWindowTitle(f"Modifica {name}" if self._is_edit else "Nuovo server MCP")
        self.setMinimumWidth(520)
        self.setStyleSheet(APP_STYLESHEET)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        heading = QLabel(f"Modifica {name}" if self._is_edit else "Aggiungi server MCP")
        _apply_compact_heading(heading, 14)
        layout.addWidget(heading)
        layout.addWidget(_make_divider())

        lbl_name = QLabel("Identificativo")
        lbl_name.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.name_input = QLineEdit(name)
        self.name_input.setFont(_mono_font(10))
        self.name_input.setPlaceholderText("es. streak, postgres-local")
        if self._is_edit:
            self.name_input.setReadOnly(True)
        layout.addWidget(lbl_name)
        layout.addWidget(self.name_input)

        lbl_mode = QLabel("Trasporto")
        lbl_mode.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [
                "Streamable HTTP (serverUrl)",
                "Bridge Legacy SSE (npx -y mcp-remote)",
                "Locale Stdio (command + args)",
            ]
        )
        layout.addWidget(lbl_mode)
        layout.addWidget(self.mode_combo)

        self.stack = QStackedWidget()

        # Page 0: Remote / Bridge
        remote_page = QWidget()
        remote_layout = QVBoxLayout(remote_page)
        remote_layout.setContentsMargins(0, 4, 0, 0)
        remote_layout.setSpacing(10)

        lbl_url = QLabel("Endpoint URL")
        lbl_url.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.remote_url_input = QLineEdit()
        self.remote_url_input.setFont(_mono_font(10))
        self.remote_url_input.setPlaceholderText("https://api.streak.com/mcp")
        remote_layout.addWidget(lbl_url)
        remote_layout.addWidget(self.remote_url_input)

        lbl_hdr = QLabel("Headers HTTP (opzionale, Chiave: Valore per riga)")
        lbl_hdr.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.remote_headers_input = QPlainTextEdit()
        self.remote_headers_input.setFont(_mono_font(10))
        self.remote_headers_input.setPlaceholderText("Authorization: Bearer ...")
        self.remote_headers_input.setFixedHeight(84)
        remote_layout.addWidget(lbl_hdr)
        remote_layout.addWidget(self.remote_headers_input)
        self.stack.addWidget(remote_page)

        # Page 1: Stdio
        stdio_page = QWidget()
        stdio_layout = QVBoxLayout(stdio_page)
        stdio_layout.setContentsMargins(0, 4, 0, 0)
        stdio_layout.setSpacing(10)

        lbl_cmd = QLabel("Comando")
        lbl_cmd.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.stdio_cmd_input = QLineEdit()
        self.stdio_cmd_input.setFont(_mono_font(10))
        self.stdio_cmd_input.setPlaceholderText("uvx, npx, python3")
        stdio_layout.addWidget(lbl_cmd)
        stdio_layout.addWidget(self.stdio_cmd_input)

        lbl_args = QLabel("Argomenti (uno per riga o separati da spazio)")
        lbl_args.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.stdio_args_input = QPlainTextEdit()
        self.stdio_args_input.setFont(_mono_font(10))
        self.stdio_args_input.setFixedHeight(74)
        stdio_layout.addWidget(lbl_args)
        stdio_layout.addWidget(self.stdio_args_input)

        lbl_env = QLabel("Variabili ambiente (CHIAVE=VALORE per riga)")
        lbl_env.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.stdio_env_input = QPlainTextEdit()
        self.stdio_env_input.setFont(_mono_font(10))
        self.stdio_env_input.setFixedHeight(74)
        stdio_layout.addWidget(lbl_env)
        stdio_layout.addWidget(self.stdio_env_input)
        self.stack.addWidget(stdio_page)

        layout.addWidget(self.stack)

        self.enabled_checkbox = QCheckBox("Attivo in Antigravity")
        self.enabled_checkbox.setChecked(True)
        layout.addWidget(self.enabled_checkbox)

        layout.addWidget(_make_divider())

        actions_row = QHBoxLayout()
        actions_row.addStretch(1)
        cancel_btn = QPushButton("Annulla")
        cancel_btn.setObjectName("GhostButton")
        save_btn = QPushButton("Salva")
        save_btn.setObjectName("PrimaryButton")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._on_accept)
        actions_row.addWidget(cancel_btn)
        actions_row.addWidget(save_btn)
        layout.addLayout(actions_row)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        if entry is not None:
            self._populate_from_entry(entry)
        else:
            self.mode_combo.setCurrentIndex(default_mode)
            self._on_mode_changed(default_mode)

        self._result: tuple[str, dict[str, Any]] | None = None

    def _on_mode_changed(self, index: int) -> None:
        self.stack.setCurrentIndex(0 if index in (self.MODE_REMOTE, self.MODE_BRIDGE) else 1)

    def _populate_from_entry(self, entry: dict[str, Any]) -> None:
        self.enabled_checkbox.setChecked(not bool(entry.get("disabled", False)))
        kind = MCPConfigManager.classify_server(entry)
        if kind == "remote":
            self.mode_combo.setCurrentIndex(self.MODE_REMOTE)
            self.remote_url_input.setText(str(entry.get("serverUrl") or entry.get("url") or ""))
            headers = entry.get("headers") or {}
            if isinstance(headers, dict) and headers:
                self.remote_headers_input.setPlainText(
                    "\n".join(f"{k}: {v}" for k, v in headers.items())
                )
        elif kind == "bridge":
            self.mode_combo.setCurrentIndex(self.MODE_BRIDGE)
            url, headers = _extract_bridge_details(entry)
            self.remote_url_input.setText(url)
            if headers:
                self.remote_headers_input.setPlainText(
                    "\n".join(f"{k}: {v}" for k, v in headers.items())
                )
        else:
            self.mode_combo.setCurrentIndex(self.MODE_STDIO)
            self.stdio_cmd_input.setText(str(entry.get("command", "")))
            args = [str(a) for a in entry.get("args", [])]
            if args:
                self.stdio_args_input.setPlainText("\n".join(args))
            env = entry.get("env") or {}
            if isinstance(env, dict) and env:
                self.stdio_env_input.setPlainText(
                    "\n".join(f"{k}={v}" for k, v in env.items())
                )
        self._on_mode_changed(self.mode_combo.currentIndex())

    def _parse_args(self) -> list[str]:
        raw = self.stdio_args_input.toPlainText().strip()
        if not raw:
            return []
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) == 1 and (" " in lines[0] or "\t" in lines[0]):
            return shlex.split(lines[0])
        return lines

    def _on_accept(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Campo mancante", "Inserisci il nome del server.")
            return

        disabled = not self.enabled_checkbox.isChecked()
        mode = self.mode_combo.currentIndex()
        try:
            if mode in (self.MODE_REMOTE, self.MODE_BRIDGE):
                url = normalize_url(self.remote_url_input.text())
                headers = parse_headers_text(self.remote_headers_input.toPlainText())
                if mode == self.MODE_BRIDGE:
                    args = ["-y", "mcp-remote", url]
                    for key, value in headers.items():
                        args.extend(["--header", f"{key}: {value}"])
                    entry: dict[str, Any] = {
                        "command": "npx",
                        "args": args,
                        "disabled": disabled,
                    }
                else:
                    entry = {"serverUrl": url, "disabled": disabled}
                    if headers:
                        entry["headers"] = headers
            else:
                cmd = self.stdio_cmd_input.text().strip()
                if not cmd:
                    raise ValueError("Inserisci il comando eseguibile.")
                args = self._parse_args()
                env = parse_env_text(self.stdio_env_input.toPlainText())
                entry = {"command": cmd, "args": args, "disabled": disabled}
                if env:
                    entry["env"] = env
        except ValueError as exc:
            QMessageBox.warning(self, "Dati non validi", str(exc))
            return

        self._result = (name, entry)
        self.accept()

    def get_result(self) -> tuple[str, dict[str, Any]] | None:
        """Return (name, entry_dict) if accepted."""
        return self._result


class MainWindow(QMainWindow):
    """Centered Linear/Vercel-style dark desktop window for agymcp."""

    def __init__(
        self,
        manager: MCPConfigManager | None = None,
        initial_url: str = "",
        check_updates_on_start: bool = True,
        auto_probe_on_change: bool = True,
    ) -> None:
        super().__init__()
        self.manager = manager or MCPConfigManager()
        self._name_manually_edited = False
        self._auto_probe_on_change = auto_probe_on_change
        self._detected_auth_type = "none"
        self._probe_worker: ProbeWorker | None = None
        self._oauth_worker: OAuthLoginWorker | None = None
        self._oauth_mode_is_reauth = False
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_install_worker: UpdateInstallWorker | None = None
        self._pending_update: UpdateInfo | None = None
        self._manual_update_check = False
        self._settings = load_settings()
        self.server_rows: list[QWidget] = []

        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.setInterval(600)
        self._probe_timer.timeout.connect(self._auto_probe_current_url)

        self.setWindowTitle(f"agymcp · v{__version__}")
        self.setMinimumSize(940, 720)
        self.setStyleSheet(APP_STYLESHEET)

        icon_path = Path(__file__).resolve().parent.parent / "assets" / "agymcp.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Spacious #09090B Canvas with centered max-width container (~30-35% breathing room)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.setCentralWidget(scroll)

        canvas = QWidget()
        canvas_layout = QHBoxLayout(canvas)
        canvas_layout.setContentsMargins(48, 40, 48, 48)
        canvas_layout.addStretch(1)

        container = QWidget()
        container.setMaximumWidth(740)
        container.setMinimumWidth(640)
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_line = QHBoxLayout()
        title_line.setSpacing(10)

        title_label = QLabel("agymcp")
        _apply_compact_heading(title_label, 18)
        version_label = QLabel(f"v{__version__}")
        version_label.setFont(_mono_font(10))
        version_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")

        title_line.addWidget(title_label)
        title_line.addWidget(version_label)
        title_line.addStretch(1)

        subtitle_label = QLabel("Antigravity MCP Installer & Manager")
        subtitle_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px;")

        title_col.addLayout(title_line)
        title_col.addWidget(subtitle_label)
        header_row.addLayout(title_col)
        header_row.addStretch(1)

        self.auto_update_checkbox = QCheckBox("Auto-aggiorna")
        self.auto_update_checkbox.setChecked(bool(self._settings.get("auto_update", True)))
        self.check_update_btn = QPushButton("Aggiornamenti")
        self.check_update_btn.setObjectName("GhostButton")

        header_row.addWidget(self.auto_update_checkbox)
        header_row.addWidget(self.check_update_btn)
        root_layout.addLayout(header_row)

        # Optional minimal Update Banner
        self.update_banner = QFrame()
        self.update_banner.setObjectName("UpdateBanner")
        self.update_banner.setVisible(False)
        banner_layout = QHBoxLayout(self.update_banner)
        banner_layout.setContentsMargins(16, 12, 16, 12)
        banner_layout.setSpacing(10)

        self.update_dot = _make_status_dot(COLOR_DOT_OK)
        self.update_banner_label = QLabel("")
        self.update_banner_label.setFont(_mono_font(10))
        self.update_banner_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        self.update_banner_label.setWordWrap(True)

        self.update_now_btn = QPushButton("Aggiorna")
        self.update_now_btn.setObjectName("GhostButton")
        self.update_now_btn.setVisible(False)
        self.restart_app_btn = QPushButton("Riavvia")
        self.restart_app_btn.setObjectName("GhostButton")
        self.restart_app_btn.setVisible(False)

        banner_layout.addWidget(self.update_dot)
        banner_layout.addWidget(self.update_banner_label, stretch=1)
        banner_layout.addWidget(self.update_now_btn)
        banner_layout.addWidget(self.restart_app_btn)

        root_layout.addSpacing(20)
        root_layout.addWidget(self.update_banner)
        root_layout.addSpacing(28)

        # ── Section 1: Quick Install Card (#121214, p-6 = 24px, zero nested cards) ──
        quick_card = QFrame()
        quick_card.setObjectName("Card")
        quick_layout = QVBoxLayout(quick_card)
        quick_layout.setContentsMargins(24, 24, 24, 24)
        quick_layout.setSpacing(16)

        quick_header = QHBoxLayout()
        quick_title = QLabel("Installa da link")
        _apply_compact_heading(quick_title, 13)
        quick_header.addWidget(quick_title)
        quick_header.addStretch(1)

        self.paste_btn = QPushButton("Incolla")
        self.paste_btn.setObjectName("GhostButton")
        self.test_btn = QPushButton("Verifica")
        self.test_btn.setObjectName("GhostButton")
        quick_header.addWidget(self.paste_btn)
        quick_header.addWidget(self.test_btn)
        quick_layout.addLayout(quick_header)

        # URL + Name row
        inputs_row = QHBoxLayout()
        inputs_row.setSpacing(10)

        self.url_input = QLineEdit()
        self.url_input.setFont(_mono_font(10))
        self.url_input.setPlaceholderText("https://api.streak.com/mcp")
        self.url_input.setMinimumHeight(38)

        self.name_input = QLineEdit()
        self.name_input.setFont(_mono_font(10))
        self.name_input.setPlaceholderText("id server")
        self.name_input.setFixedWidth(160)
        self.name_input.setMinimumHeight(38)

        self.install_btn = QPushButton("Installa")
        self.install_btn.setObjectName("PrimaryButton")
        self.install_btn.setMinimumHeight(38)

        inputs_row.addWidget(self.url_input, stretch=1)
        inputs_row.addWidget(self.name_input)
        inputs_row.addWidget(self.install_btn)
        quick_layout.addLayout(inputs_row)

        # Minimal 6px status dot + monospace telemetry row
        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        self.status_dot = _make_status_dot(COLOR_DOT_IDLE)
        self.status_label = QLabel("Incolla un endpoint MCP per la verifica automatica")
        self.status_label.setFont(_mono_font(9))
        self.status_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        self.status_label.setWordWrap(True)
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_label, stretch=1)

        self.advanced_toggle_btn = QPushButton("Opzioni auth / bridge")
        self.advanced_toggle_btn.setObjectName("GhostButton")
        self.advanced_toggle_btn.setCheckable(True)
        status_row.addWidget(self.advanced_toggle_btn)
        quick_layout.addLayout(status_row)

        # Collapsible Auth & Bridge section separated by 1px #1F1F23 divider (NO nested card!)
        self.advanced_panel = QWidget()
        self.advanced_panel.setVisible(False)
        adv_layout = QVBoxLayout(self.advanced_panel)
        adv_layout.setContentsMargins(0, 4, 0, 0)
        adv_layout.setSpacing(12)
        adv_layout.addWidget(_make_divider())

        auth_row = QHBoxLayout()
        auth_row.setSpacing(10)
        auth_lbl = QLabel("Autenticazione")
        auth_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
        self.auth_combo = QComboBox()
        self.auth_combo.addItems(
            [
                "Nessuna / OAuth automatico",
                "Bearer Token",
                "API Key Header",
                "Header personalizzati",
            ]
        )
        auth_row.addWidget(auth_lbl)
        auth_row.addWidget(self.auth_combo, stretch=1)
        adv_layout.addLayout(auth_row)

        self.auth_stack = QStackedWidget()

        none_lbl = QLabel("Nessun header statico. Antigravity gestirà OAuth se richiesto dal server.")
        none_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; font-size: 12px;")
        self.auth_stack.addWidget(none_lbl)

        self.bearer_input = QLineEdit()
        self.bearer_input.setFont(_mono_font(10))
        self.bearer_input.setPlaceholderText("Bearer token...")
        self.bearer_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        self.auth_stack.addWidget(self.bearer_input)

        apikey_widget = QWidget()
        apikey_row = QHBoxLayout(apikey_widget)
        apikey_row.setContentsMargins(0, 0, 0, 0)
        apikey_row.setSpacing(8)
        self.apikey_header_input = QLineEdit("X-Api-Key")
        self.apikey_header_input.setFont(_mono_font(10))
        self.apikey_header_input.setFixedWidth(160)
        self.apikey_value_input = QLineEdit()
        self.apikey_value_input.setFont(_mono_font(10))
        self.apikey_value_input.setPlaceholderText("Valore chiave...")
        self.apikey_value_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        apikey_row.addWidget(self.apikey_header_input)
        apikey_row.addWidget(self.apikey_value_input, stretch=1)
        self.auth_stack.addWidget(apikey_widget)

        self.custom_headers_input = QPlainTextEdit()
        self.custom_headers_input.setFont(_mono_font(10))
        self.custom_headers_input.setPlaceholderText("Chiave: Valore (uno per riga)")
        self.custom_headers_input.setFixedHeight(64)
        self.auth_stack.addWidget(self.custom_headers_input)

        adv_layout.addWidget(self.auth_stack)

        self.bridge_checkbox = QCheckBox("Usa bridge npx -y mcp-remote (solo per vecchi endpoint /sse)")
        adv_layout.addWidget(self.bridge_checkbox)

        quick_layout.addWidget(self.advanced_panel)
        root_layout.addWidget(quick_card)

        # Generous 44px separation between major sections
        root_layout.addSpacing(44)

        # ── Section 2: Installed Servers / Raw JSON Tabs ────────────────────
        tabs_bar = QHBoxLayout()
        tabs_bar.setSpacing(20)

        self.tab_servers_btn = QPushButton("Server")
        self.tab_servers_btn.setObjectName("TabButton")
        self.tab_servers_btn.setProperty("active", True)

        self.tab_json_btn = QPushButton("JSON")
        self.tab_json_btn.setObjectName("TabButton")
        self.tab_json_btn.setProperty("active", False)

        self.server_count_label = QLabel("0")
        self.server_count_label.setFont(_mono_font(9))
        self.server_count_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")

        tabs_bar.addWidget(self.tab_servers_btn)
        tabs_bar.addWidget(self.server_count_label)
        tabs_bar.addWidget(self.tab_json_btn)
        tabs_bar.addStretch(1)

        self.add_stdio_btn = QPushButton("+ Server locale")
        self.add_stdio_btn.setObjectName("GhostButton")
        self.reload_btn = QPushButton("Ricarica")
        self.reload_btn.setObjectName("GhostButton")
        tabs_bar.addWidget(self.add_stdio_btn)
        tabs_bar.addWidget(self.reload_btn)
        root_layout.addLayout(tabs_bar)
        root_layout.addWidget(_make_divider())
        root_layout.addSpacing(16)

        self.content_stack = QStackedWidget()

        # Page 0: Server list card (#121214)
        servers_card = QFrame()
        servers_card.setObjectName("Card")
        servers_card_layout = QVBoxLayout(servers_card)
        servers_card_layout.setContentsMargins(24, 16, 24, 16)
        servers_card_layout.setSpacing(0)

        self.servers_list_layout = QVBoxLayout()
        self.servers_list_layout.setContentsMargins(0, 0, 0, 0)
        self.servers_list_layout.setSpacing(0)
        servers_card_layout.addLayout(self.servers_list_layout)
        servers_card_layout.addStretch(1)

        self.content_stack.addWidget(servers_card)

        # Page 1: Raw JSON card (#121214)
        raw_card = QFrame()
        raw_card.setObjectName("Card")
        raw_layout = QVBoxLayout(raw_card)
        raw_layout.setContentsMargins(24, 24, 24, 24)
        raw_layout.setSpacing(14)

        self.raw_editor = QPlainTextEdit()
        self.raw_editor.setFont(_mono_font(10))
        self.raw_editor.setMinimumHeight(280)
        raw_layout.addWidget(self.raw_editor)

        raw_bar = QHBoxLayout()
        raw_bar.setSpacing(8)
        self.format_raw_btn = QPushButton("Formatta")
        self.format_raw_btn.setObjectName("GhostButton")
        self.restore_bak_btn = QPushButton("Ripristina .bak")
        self.restore_bak_btn.setObjectName("GhostButton")
        self.save_raw_btn = QPushButton("Salva JSON")
        self.save_raw_btn.setObjectName("PrimaryButton")

        raw_bar.addWidget(self.format_raw_btn)
        raw_bar.addWidget(self.restore_bak_btn)
        raw_bar.addStretch(1)
        raw_bar.addWidget(self.save_raw_btn)
        raw_layout.addLayout(raw_bar)

        self.content_stack.addWidget(raw_card)
        root_layout.addWidget(self.content_stack)

        # Footer config path (minimal monospace)
        root_layout.addSpacing(20)
        self.config_path_label = QLabel(str(self.manager.config_path))
        self.config_path_label.setFont(_mono_font(9))
        self.config_path_label.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")
        self.config_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        root_layout.addWidget(self.config_path_label)
        root_layout.addStretch(1)

        canvas_layout.addWidget(container)
        canvas_layout.addStretch(1)
        scroll.setWidget(canvas)

        # Signal wiring
        self.url_input.textChanged.connect(self._on_url_changed)
        self.name_input.textEdited.connect(self._on_name_edited)
        self.paste_btn.clicked.connect(self._paste_from_clipboard)
        self.advanced_toggle_btn.toggled.connect(self._toggle_advanced)
        self.auth_combo.currentIndexChanged.connect(self.auth_stack.setCurrentIndex)
        self.test_btn.clicked.connect(self._start_probe)
        self.install_btn.clicked.connect(self.install_from_quick_bar)
        self.add_stdio_btn.clicked.connect(self._add_stdio_server_dialog)
        self.reload_btn.clicked.connect(self.refresh_all)
        self.tab_servers_btn.clicked.connect(lambda: self._switch_tab(0))
        self.tab_json_btn.clicked.connect(lambda: self._switch_tab(1))
        self.save_raw_btn.clicked.connect(self._save_raw_json)
        self.format_raw_btn.clicked.connect(self._format_raw_json)
        self.restore_bak_btn.clicked.connect(self._restore_backup)
        self.auto_update_checkbox.toggled.connect(self._on_auto_update_toggled)
        self.check_update_btn.clicked.connect(lambda: self._start_update_check(manual=True))
        self.update_now_btn.clicked.connect(self._start_update_install)
        self.restart_app_btn.clicked.connect(self._restart_application)

        self.refresh_all()
        if initial_url:
            self.url_input.setText(initial_url)
        if check_updates_on_start:
            self._start_update_check(manual=False)

    def _switch_tab(self, index: int) -> None:
        self.content_stack.setCurrentIndex(index)
        self.tab_servers_btn.setProperty("active", index == 0)
        self.tab_json_btn.setProperty("active", index == 1)
        self.tab_servers_btn.style().unpolish(self.tab_servers_btn)
        self.tab_servers_btn.style().polish(self.tab_servers_btn)
        self.tab_json_btn.style().unpolish(self.tab_json_btn)
        self.tab_json_btn.style().polish(self.tab_json_btn)

    def _set_status(self, text: str, kind: str = "idle") -> None:
        dot_colors = {
            "idle": COLOR_DOT_IDLE,
            "info": COLOR_TEXT_SECONDARY,
            "ok": COLOR_DOT_OK,
            "warn": COLOR_DOT_WARN,
            "err": COLOR_DOT_ERR,
        }
        dot_color = dot_colors.get(kind, COLOR_DOT_IDLE)
        self.status_dot.setStyleSheet(
            f"background-color: {dot_color}; border-radius: 3px; border: none;"
        )
        text_color = COLOR_TEXT_MUTED if kind == "idle" else COLOR_TEXT_SECONDARY
        self.status_label.setStyleSheet(f"color: {text_color};")
        self.status_label.setText(text)

    def _toggle_advanced(self, expanded: bool) -> None:
        self.advanced_panel.setVisible(expanded)

    def _paste_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            text = clipboard.text().strip()
            if text:
                self.url_input.setText(text)
            else:
                self._set_status("Appunti vuoti", "warn")

    def _on_url_changed(self, text: str) -> None:
        stripped = text.strip()
        self._probe_timer.stop()
        self._detected_auth_type = "none"
        self.install_btn.setText("Installa")
        if not stripped:
            self._name_manually_edited = False
            self.name_input.clear()
            self.bridge_checkbox.setChecked(False)
            self._set_status("Incolla un endpoint MCP per la verifica automatica", "idle")
            return

        if not self._name_manually_edited:
            self.name_input.setText(infer_server_name(stripped))

        if is_sse_url(stripped):
            self.bridge_checkbox.setChecked(True)
            self._set_status("Endpoint /sse · bridge npx mcp-remote preselezionato", "warn")

        if self._auto_probe_on_change and "." in stripped and len(stripped) >= 8:
            self._probe_timer.start()

    def _auto_probe_current_url(self) -> None:
        raw_url = self.url_input.text().strip()
        if not raw_url:
            return
        try:
            normalize_url(raw_url)
        except ValueError:
            return
        self._start_probe()

    def _on_name_edited(self, text: str) -> None:
        self._name_manually_edited = bool(text.strip())

    def _collect_quick_headers(self) -> dict[str, str]:
        mode = self.auth_combo.currentIndex()
        if mode == 0:
            return {}
        if mode == 1:
            token = self.bearer_input.text().strip()
            if not token:
                raise ValueError("Inserisci il Bearer token o scegli 'Nessuna / OAuth'.")
            if token.lower().startswith("bearer "):
                token = token[7:].strip()
            return {"Authorization": f"Bearer {token}"}
        if mode == 2:
            hdr_name = self.apikey_header_input.text().strip()
            hdr_val = self.apikey_value_input.text().strip()
            if not hdr_name or not hdr_val:
                raise ValueError("Inserisci nome header e valore API Key.")
            return {hdr_name: hdr_val}
        return parse_headers_text(self.custom_headers_input.toPlainText())

    def _start_probe(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            self._set_status("Inserisci un link MCP prima di verificare", "warn")
            return
        try:
            headers = self._collect_quick_headers()
        except ValueError as exc:
            self._set_status(str(exc), "err")
            return

        if self._probe_worker is not None and self._probe_worker.isRunning():
            return

        self.test_btn.setEnabled(False)
        self._set_status("Handshake MCP (claude-code) in corso...", "info")
        self._probe_worker = ProbeWorker(url, headers=headers, parent=self)
        self._probe_worker.finished_probe.connect(self._on_probe_finished)
        self._probe_worker.start()

    def _on_probe_finished(self, probed_url: str, result: dict[str, Any]) -> None:
        self.test_btn.setEnabled(True)
        # Ignore stale responses if the user already changed the URL
        if probed_url.strip() != self.url_input.text().strip():
            return

        if result.get("is_legacy_sse"):
            self.bridge_checkbox.setChecked(True)

        suggested = str(result.get("suggested_name") or "").strip()
        if suggested and not self._name_manually_edited:
            self.name_input.setText(suggested)

        if result.get("reachable"):
            auth_type = str(result.get("auth_type") or "none")
            self._detected_auth_type = auth_type
            if auth_type == "oauth" and self.auth_combo.currentIndex() == 0 and not self.bridge_checkbox.isChecked():
                self.install_btn.setText("Accedi e Installa")
            else:
                self.install_btn.setText("Installa")
            kind = "warn" if result.get("needs_auth") else "ok"
            self._set_status(str(result.get("message", "Endpoint attivo")), kind)
        else:
            self._detected_auth_type = "none"
            self.install_btn.setText("Installa")
            self._set_status(str(result.get("message", "Endpoint non raggiungibile")), "err")

    def install_from_quick_bar(self, confirm_overwrite: bool = True) -> bool:
        """Validate quick-install inputs and write the remote server (or run OAuth flow)."""
        raw_url = self.url_input.text().strip()
        if not raw_url:
            self._set_status("Incolla prima il link del server MCP", "err")
            return False

        try:
            norm_url = normalize_url(raw_url)
            headers = self._collect_quick_headers()
        except ValueError as exc:
            self._set_status(str(exc), "err")
            return False

        name = self.name_input.text().strip() or infer_server_name(norm_url)
        existing = self.manager.get_servers()
        if confirm_overwrite and name in existing:
            reply = QMessageBox.question(
                self,
                "Server già presente",
                f"Il server '{name}' esiste già.\nVuoi aggiornarlo con il nuovo URL?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        use_bridge = self.bridge_checkbox.isChecked()
        if (
            self._detected_auth_type == "oauth"
            and not headers
            and not use_bridge
            and self.auth_combo.currentIndex() == 0
        ):
            self._start_oauth_flow(name=name, url=norm_url, is_reauth=False)
            return True

        self.manager.add_remote_server(
            name=name,
            url=norm_url,
            headers=headers,
            use_bridge=use_bridge,
            disabled=False,
        )
        self.refresh_all()
        mode_desc = "bridge" if use_bridge else "http"
        self._set_status(f"Installato '{name}' ({mode_desc}) in Antigravity", "ok")
        return True

    def _start_oauth_flow(
        self,
        name: str,
        url: str,
        is_reauth: bool = False,
    ) -> None:
        if self._oauth_worker is not None and self._oauth_worker.isRunning():
            return
        self._oauth_mode_is_reauth = is_reauth
        self.install_btn.setEnabled(False)
        self.test_btn.setEnabled(False)
        self._set_status("Avvio autenticazione OAuth 2.1 nel browser...", "info")
        self._oauth_worker = OAuthLoginWorker(
            server_name=name,
            url=url,
            try_refresh_first=is_reauth,
            parent=self,
        )
        self._oauth_worker.status_update.connect(
            lambda msg: self._set_status(msg, "info")
        )
        self._oauth_worker.finished_oauth.connect(self._on_oauth_finished)
        self._oauth_worker.start()

    def _on_oauth_finished(
        self,
        server_name: str,
        url: str,
        token: OAuthTokenResult | None,
        error: str,
        probe: dict[str, Any],
    ) -> None:
        self.install_btn.setEnabled(True)
        self.test_btn.setEnabled(True)

        if error or token is None:
            self._set_status(f"OAuth fallito · {error}", "err")
            return

        if self._oauth_mode_is_reauth:
            servers = self.manager.get_servers()
            entry = servers.get(server_name, {"serverUrl": url, "disabled": False})
            headers = dict(entry.get("headers") or {})
            headers["Authorization"] = f"Bearer {token.access_token}"
            entry["headers"] = headers
            self.manager.set_server_entry(server_name, entry)
        else:
            self.manager.add_remote_server(
                name=server_name,
                url=url,
                headers={"Authorization": f"Bearer {token.access_token}"},
                use_bridge=False,
                disabled=False,
            )

        self._detected_auth_type = "none"
        self.install_btn.setText("Installa")
        self.refresh_all()

        tools_count = probe.get("tools_count")
        extra = f" · {tools_count} tools verificati" if tools_count is not None else ""
        action_word = "rinnovato" if self._oauth_mode_is_reauth else "autenticato e installato"
        self._set_status(f"Server '{server_name}' {action_word}{extra}", "ok")

    def _clear_server_rows(self) -> None:
        self.server_rows.clear()
        while self.servers_list_layout.count():
            item = self.servers_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_server_row(self, name: str, entry: dict[str, Any]) -> QFrame:
        row = QFrame()
        row.setObjectName("ServerRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 12, 8, 12)
        row_layout.setSpacing(12)

        enabled = not bool(entry.get("disabled", False))
        dot = _make_status_dot(COLOR_DOT_OK if enabled else COLOR_DOT_IDLE)
        row_layout.addWidget(dot)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        top_line = QHBoxLayout()
        top_line.setSpacing(8)

        name_lbl = QLabel(name)
        name_font = QFont()
        name_font.setWeight(QFont.Weight.DemiBold)
        name_lbl.setFont(name_font)
        name_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY if enabled else COLOR_TEXT_MUTED};"
        )

        kind = MCPConfigManager.classify_server(entry)
        kind_map = {"remote": "http", "bridge": "sse-bridge", "stdio": "stdio"}
        kind_lbl = QLabel(kind_map.get(kind, kind))
        kind_lbl.setFont(_mono_font(9))
        kind_lbl.setStyleSheet(f"color: {COLOR_TEXT_MUTED};")

        top_line.addWidget(name_lbl)
        top_line.addWidget(kind_lbl)
        top_line.addStretch(1)

        endpoint = MCPConfigManager.get_server_endpoint(entry)
        secrets = MCPConfigManager.summarize_secrets_count(entry)
        endpoint_lbl = QLabel(f"{endpoint}{secrets}")
        endpoint_lbl.setFont(_mono_font(9))
        endpoint_lbl.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY};")
        endpoint_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        info_col.addLayout(top_line)
        info_col.addWidget(endpoint_lbl)
        row_layout.addLayout(info_col, stretch=1)

        # Progressive Disclosure: single contextual '...' menu button
        menu_btn = QPushButton("···")
        menu_btn.setObjectName("RowMenuButton")
        menu_btn.setFixedWidth(34)
        menu_btn.clicked.connect(
            lambda _checked=False, btn=menu_btn, srv=name, ent=entry, en=enabled: (
                self._open_row_menu(btn, srv, ent, en)
            )
        )
        row_layout.addWidget(menu_btn)
        return row

    def _open_row_menu(
        self,
        anchor: QPushButton,
        name: str,
        entry: dict[str, Any],
        enabled: bool,
    ) -> None:
        menu = QMenu(self)
        toggle_action = menu.addAction("Disattiva" if enabled else "Attiva")
        edit_action = menu.addAction("Modifica")
        oauth_action = None
        if MCPConfigManager.classify_server(entry) == "remote":
            oauth_action = menu.addAction("Autentica / Rinnova OAuth")
        menu.addSeparator()
        delete_action = menu.addAction("Elimina")

        chosen = menu.exec(anchor.mapToGlobal(anchor.rect().bottomRight()))
        if chosen == toggle_action:
            self._on_toggle_server(name, not enabled)
        elif chosen == edit_action:
            self._edit_server(name, entry)
        elif oauth_action is not None and chosen == oauth_action:
            url = MCPConfigManager.get_server_endpoint(entry)
            if url:
                self._start_oauth_flow(name=name, url=url, is_reauth=True)
        elif chosen == delete_action:
            self._delete_server(name)

    def refresh_all(self) -> None:
        """Reload server list and raw JSON editor from disk."""
        try:
            servers = self.manager.get_servers()
            raw_text = self.manager.load_raw_text()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Errore lettura config · {exc}", "err")
            return

        self._clear_server_rows()
        sorted_items = sorted(servers.items())
        self.server_count_label.setText(str(len(sorted_items)))

        if not sorted_items:
            empty = QLabel("Nessun server MCP configurato.")
            empty.setStyleSheet(f"color: {COLOR_TEXT_MUTED}; padding: 20px 8px;")
            self.servers_list_layout.addWidget(empty)
        else:
            for idx, (name, entry) in enumerate(sorted_items):
                if idx > 0:
                    self.servers_list_layout.addWidget(_make_divider())
                row = self._build_server_row(name, entry)
                self.servers_list_layout.addWidget(row)
                self.server_rows.append(row)

        self.raw_editor.setPlainText(raw_text)
        self.restore_bak_btn.setEnabled(self.manager.backup_path.exists())

    def _on_toggle_server(self, name: str, enabled: bool) -> None:
        try:
            self.manager.set_server_enabled(name, enabled)
            state_txt = "attivato" if enabled else "disattivato"
            self.refresh_all()
            self._set_status(f"Server '{name}' {state_txt}", "ok" if enabled else "idle")
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Errore aggiornamento '{name}' · {exc}", "err")

    def _add_stdio_server_dialog(self) -> None:
        dialog = ServerEditDialog(
            parent=self,
            default_mode=ServerEditDialog.MODE_STDIO,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result is not None:
                name, entry = result
                self.manager.set_server_entry(name, entry)
                self.refresh_all()
                self._set_status(f"Server '{name}' salvato", "ok")

    def _edit_server(self, name: str, entry: dict[str, Any]) -> None:
        dialog = ServerEditDialog(parent=self, name=name, entry=entry)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result is not None:
                srv_name, new_entry = result
                self.manager.set_server_entry(srv_name, new_entry)
                self.refresh_all()
                self._set_status(f"Server '{srv_name}' aggiornato", "ok")

    def _delete_server(self, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Elimina server",
            f"Rimuovere '{name}' dalla configurazione di Antigravity?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.manager.remove_server(name):
            self.refresh_all()
            self._set_status(f"Server '{name}' rimosso", "idle")

    def _format_raw_json(self) -> None:
        try:
            parsed = json.loads(self.raw_editor.toPlainText())
            self.raw_editor.setPlainText(
                json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
            )
            self._set_status("JSON formattato", "info")
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "JSON non valido", f"Errore di sintassi JSON:\n{exc}")

    def _save_raw_json(self) -> None:
        try:
            self.manager.save_raw_text(self.raw_editor.toPlainText())
            self.refresh_all()
            self._set_status("JSON salvato (backup .bak creato)", "ok")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Errore salvataggio JSON", str(exc))

    def _restore_backup(self) -> None:
        if not self.manager.backup_path.exists():
            self._set_status("Nessun backup .bak trovato", "warn")
            return
        reply = QMessageBox.question(
            self,
            "Ripristina backup",
            f"Ripristinare {self.manager.config_path.name} dall'ultimo .bak?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.manager.restore_backup():
                self.refresh_all()
                self._set_status("Configurazione ripristinata da .bak", "ok")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Errore ripristino", str(exc))

    def _on_auto_update_toggled(self, enabled: bool) -> None:
        self._settings["auto_update"] = bool(enabled)
        save_settings(self._settings)

    def _start_update_check(self, manual: bool = False) -> None:
        if self._update_check_worker is not None and self._update_check_worker.isRunning():
            return
        self._manual_update_check = manual
        self.check_update_btn.setEnabled(False)
        if manual:
            self._set_status("Controllo aggiornamenti su GitHub...", "info")
        self._update_check_worker = UpdateCheckWorker(parent=self)
        self._update_check_worker.finished_check.connect(self._on_update_check_finished)
        self._update_check_worker.start()

    def _on_update_check_finished(self, info: UpdateInfo) -> None:
        self.check_update_btn.setEnabled(True)
        if info.error:
            if self._manual_update_check:
                self._set_status(info.error, "warn")
            return

        if not info.update_available:
            if self._manual_update_check:
                self._set_status(f"agymcp v{info.current_version} è già aggiornato", "ok")
            return

        self._pending_update = info
        self.update_banner.setVisible(True)
        self.restart_app_btn.setVisible(False)
        if self.auto_update_checkbox.isChecked():
            self.update_now_btn.setVisible(False)
            self.update_banner_label.setText(
                f"v{info.latest_version} disponibile · installazione automatica..."
            )
            self._start_update_install()
        else:
            self.update_now_btn.setVisible(True)
            self.update_banner_label.setText(
                f"v{info.latest_version} disponibile (attuale v{info.current_version})"
            )

    def _start_update_install(self) -> None:
        if self._pending_update is None:
            return
        if self._update_install_worker is not None and self._update_install_worker.isRunning():
            return
        self.update_now_btn.setEnabled(False)
        self.update_banner_label.setText(
            f"Installazione v{self._pending_update.latest_version} in corso..."
        )
        self._update_install_worker = UpdateInstallWorker(
            self._pending_update, parent=self
        )
        self._update_install_worker.finished_install.connect(
            self._on_update_install_finished
        )
        self._update_install_worker.start()

    def _on_update_install_finished(self, result: UpdateResult) -> None:
        self.update_now_btn.setEnabled(True)
        if result.success:
            self.update_dot.setStyleSheet(
                f"background-color: {COLOR_DOT_OK}; border-radius: 3px; border: none;"
            )
            self.update_now_btn.setVisible(False)
            self.restart_app_btn.setVisible(result.restart_required)
            self.update_banner_label.setText(
                f"v{result.new_version} installata · riavvia per applicare"
            )
            self._set_status(result.message, "ok")
        else:
            self.update_dot.setStyleSheet(
                f"background-color: {COLOR_DOT_ERR}; border-radius: 3px; border: none;"
            )
            self.update_now_btn.setVisible(True)
            self.update_banner_label.setText(result.message)
            self._set_status(result.message, "err")

    def _restart_application(self) -> None:
        launcher = Path.home() / ".local" / "bin" / "agymcp"
        if launcher.exists() and os.access(launcher, os.X_OK):
            os.execv(str(launcher), [str(launcher)])
        system_bin = Path("/usr/bin/agymcp")
        if system_bin.exists() and os.access(system_bin, os.X_OK):
            os.execv(str(system_bin), [str(system_bin)])
        os.execv(sys.executable, [sys.executable, "-m", "agymcp.cli"])


def launch_gui(
    manager: MCPConfigManager | None = None,
    initial_url: str = "",
) -> int:
    """Launch the PyQt6 desktop application."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("agymcp")
    app.setDesktopFileName("agymcp")
    window = MainWindow(manager=manager, initial_url=initial_url)
    window.show()
    return app.exec()
