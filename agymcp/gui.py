"""Native PyQt6 desktop interface for agymcp."""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
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
from agymcp.updater import (
    UpdateInfo,
    UpdateResult,
    apply_update,
    check_for_updates,
    load_settings,
    save_settings,
)


class UpdateCheckWorker(QThread):
    """Background thread to check GitHub Releases for a newer agymcp version."""

    finished_check = pyqtSignal(object)

    def run(self) -> None:
        self.finished_check.emit(check_for_updates())


class UpdateInstallWorker(QThread):
    """Background thread to download and install an available agymcp release."""

    finished_install = pyqtSignal(object)

    def __init__(self, info: UpdateInfo, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.info = info

    def run(self) -> None:
        self.finished_install.emit(apply_update(self.info))


class ProbeWorker(QThread):
    """Background thread to probe an MCP HTTP URL without freezing the UI."""

    finished_probe = pyqtSignal(dict)

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
        self.finished_probe.emit(result)


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
    """Modal dialog for creating or editing a Remote, Bridge, or Stdio MCP server."""

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
        self.setWindowTitle(
            f"Modifica server: {name}" if self._is_edit else "Aggiungi Server MCP"
        )
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        form_top = QFormLayout()

        self.name_input = QLineEdit(name)
        self.name_input.setPlaceholderText("es. streak, postgres-local, github")
        if self._is_edit:
            self.name_input.setReadOnly(True)
        form_top.addRow("Nome server:", self.name_input)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(
            [
                "HTTP Remoto (serverUrl)",
                "Bridge Legacy SSE (npx -y mcp-remote)",
                "Locale Stdio (command + args)",
            ]
        )
        form_top.addRow("Tipo trasporto:", self.mode_combo)
        layout.addLayout(form_top)

        self.stack = QStackedWidget()

        # Page 0: Remote / Bridge fields
        remote_page = QWidget()
        remote_form = QFormLayout(remote_page)
        self.remote_url_input = QLineEdit()
        self.remote_url_input.setPlaceholderText("https://api.streak.com/mcp")
        remote_form.addRow("URL Endpoint:", self.remote_url_input)

        self.remote_headers_input = QPlainTextEdit()
        self.remote_headers_input.setPlaceholderText(
            "Opzionale, un header per riga:\nAuthorization: Bearer tuo_token\nX-Api-Key: tua_chiave"
        )
        self.remote_headers_input.setFixedHeight(90)
        remote_form.addRow("Headers HTTP:", self.remote_headers_input)
        self.stack.addWidget(remote_page)

        # Page 1: Stdio fields
        stdio_page = QWidget()
        stdio_form = QFormLayout(stdio_page)
        self.stdio_cmd_input = QLineEdit()
        self.stdio_cmd_input.setPlaceholderText("es. uvx, npx, python3, /path/to/bin")
        stdio_form.addRow("Comando:", self.stdio_cmd_input)

        self.stdio_args_input = QPlainTextEdit()
        self.stdio_args_input.setPlaceholderText(
            "Argomenti (uno per riga oppure separati da spazio se su una sola riga)"
        )
        self.stdio_args_input.setFixedHeight(85)
        stdio_form.addRow("Argomenti:", self.stdio_args_input)

        self.stdio_env_input = QPlainTextEdit()
        self.stdio_env_input.setPlaceholderText(
            "Opzionale, una variabile per riga:\nAPI_KEY=valore"
        )
        self.stdio_env_input.setFixedHeight(80)
        stdio_form.addRow("Variabili Env:", self.stdio_env_input)
        self.stack.addWidget(stdio_page)

        layout.addWidget(self.stack)

        self.enabled_checkbox = QCheckBox("Server attivo (abilitato in Antigravity)")
        self.enabled_checkbox.setChecked(True)
        layout.addWidget(self.enabled_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Salva")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Annulla")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        if entry is not None:
            self._populate_from_entry(entry)
        else:
            self.mode_combo.setCurrentIndex(default_mode)
            self._on_mode_changed(default_mode)

        self._result: tuple[str, dict[str, Any]] | None = None

    def _on_mode_changed(self, index: int) -> None:
        if index in (self.MODE_REMOTE, self.MODE_BRIDGE):
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(1)

    def _populate_from_entry(self, entry: dict[str, Any]) -> None:
        self.enabled_checkbox.setChecked(not bool(entry.get("disabled", False)))
        kind = MCPConfigManager.classify_server(entry)
        if kind == "remote":
            self.mode_combo.setCurrentIndex(self.MODE_REMOTE)
            self.remote_url_input.setText(
                str(entry.get("serverUrl") or entry.get("url") or "")
            )
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
                    raise ValueError("Inserisci il comando eseguibile (es. uvx, npx).")
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
        """Return (name, entry_dict) if the dialog was accepted."""
        return self._result


class MainWindow(QMainWindow):
    """Main desktop window for Antigravity MCP installation and management."""

    def __init__(
        self,
        manager: MCPConfigManager | None = None,
        initial_url: str = "",
        check_updates_on_start: bool = True,
    ) -> None:
        super().__init__()
        self.manager = manager or MCPConfigManager()
        self._name_manually_edited = False
        self._probe_worker: ProbeWorker | None = None
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_install_worker: UpdateInstallWorker | None = None
        self._pending_update: UpdateInfo | None = None
        self._settings = load_settings()

        self.setWindowTitle(f"Antigravity MCP Installer — agymcp v{__version__}")
        self.setMinimumSize(820, 640)
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "agymcp.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(16, 16, 16, 16)
        root_layout.setSpacing(12)

        # Header with version & update controls
        header_row = QHBoxLayout()
        title_label = QLabel(f"Antigravity MCP Installer  (v{__version__})")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_row.addWidget(title_label)
        header_row.addStretch(1)

        self.auto_update_checkbox = QCheckBox("Auto-aggiorna")
        self.auto_update_checkbox.setChecked(bool(self._settings.get("auto_update", True)))
        self.auto_update_checkbox.setToolTip(
            "Se attivo, scarica e installa automaticamente ogni nuova release di agymcp all'avvio."
        )
        self.check_update_btn = QPushButton("Controlla aggiornamenti")
        header_row.addWidget(self.auto_update_checkbox)
        header_row.addWidget(self.check_update_btn)
        root_layout.addLayout(header_row)

        # Collapsible Update Banner (visible when an update is detected/installing/installed)
        self.update_banner = QFrame()
        self.update_banner.setFrameShape(QFrame.Shape.StyledPanel)
        self.update_banner.setStyleSheet(
            "QFrame { background-color: #1e3a8a; border-radius: 6px; padding: 6px; }"
            "QLabel { color: #f8fafc; font-weight: 500; }"
        )
        self.update_banner.setVisible(False)
        banner_layout = QHBoxLayout(self.update_banner)
        banner_layout.setContentsMargins(10, 6, 10, 6)
        self.update_banner_label = QLabel("")
        self.update_banner_label.setWordWrap(True)
        self.update_now_btn = QPushButton("Aggiorna ora")
        self.update_now_btn.setVisible(False)
        self.restart_app_btn = QPushButton("Riavvia agymcp")
        self.restart_app_btn.setVisible(False)
        banner_layout.addWidget(self.update_banner_label, stretch=1)
        banner_layout.addWidget(self.update_now_btn)
        banner_layout.addWidget(self.restart_app_btn)
        root_layout.addWidget(self.update_banner)

        subtitle_label = QLabel(
            "Incolla il link di un server MCP remoto (es. https://api.streak.com/mcp) "
            "per aggiungerlo subito ad Antigravity."
        )
        subtitle_label.setWordWrap(True)
        root_layout.addWidget(subtitle_label)

        # Top Card: Quick Link Install
        quick_group = QGroupBox("Installazione Rapida da Link (1-Click)")
        quick_layout = QVBoxLayout(quick_group)
        quick_layout.setSpacing(10)

        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://api.streak.com/mcp")
        self.url_input.setClearButtonEnabled(True)
        self.url_input.setMinimumHeight(34)

        self.paste_btn = QPushButton("Incolla")
        self.paste_btn.setMinimumHeight(34)
        self.paste_btn.setToolTip("Incolla URL dagli appunti")

        url_row.addWidget(QLabel("Link MCP:"))
        url_row.addWidget(self.url_input, stretch=1)
        url_row.addWidget(self.paste_btn)
        quick_layout.addLayout(url_row)

        name_row = QHBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nome server (auto-dedotto dal link, es. streak)")
        self.name_input.setMinimumHeight(32)
        name_row.addWidget(QLabel("Nome ID:"))
        name_row.addWidget(self.name_input, stretch=1)

        self.test_btn = QPushButton("Test Connessione")
        self.test_btn.setMinimumHeight(32)
        self.install_btn = QPushButton("Installa MCP")
        self.install_btn.setMinimumHeight(32)
        self.install_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; color: white; font-weight: bold; "
            "padding: 6px 16px; border-radius: 5px; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
            "QPushButton:disabled { background-color: #6b7280; }"
        )
        name_row.addWidget(self.test_btn)
        name_row.addWidget(self.install_btn)
        quick_layout.addLayout(name_row)

        # Collapsible Auth & Transport Options
        self.advanced_toggle_btn = QPushButton(
            "▸ Opzioni Autenticazione & Bridge (Opzionale)"
        )
        self.advanced_toggle_btn.setCheckable(True)
        self.advanced_toggle_btn.setFlat(True)
        self.advanced_toggle_btn.setStyleSheet("text-align: left; font-weight: 600;")
        quick_layout.addWidget(self.advanced_toggle_btn)

        self.advanced_panel = QFrame()
        self.advanced_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.advanced_panel.setVisible(False)
        adv_layout = QVBoxLayout(self.advanced_panel)

        auth_form = QFormLayout()
        self.auth_combo = QComboBox()
        self.auth_combo.addItems(
            [
                "Nessuna / OAuth (gestito automaticamente da Antigravity)",
                "Bearer Token (Authorization: Bearer ...)",
                "Header API Key (es. X-Api-Key / X-Goog-Api-Key)",
                "Header personalizzati (Chiave: Valore)",
            ]
        )
        auth_form.addRow("Autenticazione:", self.auth_combo)

        self.auth_stack = QStackedWidget()

        # Auth 0: None / OAuth
        none_widget = QLabel(
            "Nessun header statico verrà scritto. Se il server usa OAuth, "
            "Antigravity aprirà il flusso di accesso automaticamente."
        )
        none_widget.setWordWrap(True)
        self.auth_stack.addWidget(none_widget)

        # Auth 1: Bearer Token
        bearer_widget = QWidget()
        bearer_layout = QHBoxLayout(bearer_widget)
        bearer_layout.setContentsMargins(0, 0, 0, 0)
        self.bearer_input = QLineEdit()
        self.bearer_input.setPlaceholderText("Incolla il tuo Bearer token...")
        self.bearer_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        bearer_layout.addWidget(self.bearer_input)
        self.auth_stack.addWidget(bearer_widget)

        # Auth 2: API Key Header
        apikey_widget = QWidget()
        apikey_layout = QHBoxLayout(apikey_widget)
        apikey_layout.setContentsMargins(0, 0, 0, 0)
        self.apikey_header_input = QLineEdit("X-Api-Key")
        self.apikey_header_input.setPlaceholderText("Nome header (es. X-Api-Key)")
        self.apikey_header_input.setMaximumWidth(180)
        self.apikey_value_input = QLineEdit()
        self.apikey_value_input.setPlaceholderText("Valore API Key...")
        self.apikey_value_input.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
        apikey_layout.addWidget(self.apikey_header_input)
        apikey_layout.addWidget(self.apikey_value_input, stretch=1)
        self.auth_stack.addWidget(apikey_widget)

        # Auth 3: Custom Headers
        self.custom_headers_input = QPlainTextEdit()
        self.custom_headers_input.setPlaceholderText(
            "Un header per riga:\nX-Custom-Header: valore"
        )
        self.custom_headers_input.setFixedHeight(64)
        self.auth_stack.addWidget(self.custom_headers_input)

        auth_form.addRow("", self.auth_stack)
        adv_layout.addLayout(auth_form)

        self.bridge_checkbox = QCheckBox(
            "Usa bridge Stdio (npx -y mcp-remote) — utile solo per vecchi server legacy /sse"
        )
        adv_layout.addWidget(self.bridge_checkbox)
        quick_layout.addWidget(self.advanced_panel)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        quick_layout.addWidget(self.status_label)

        root_layout.addWidget(quick_group)

        # Bottom Tabs: Installed Servers & Raw JSON
        self.tabs = QTabWidget()

        # Tab 1: Installed Servers
        servers_tab = QWidget()
        servers_layout = QVBoxLayout(servers_tab)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Attivo", "Nome", "Tipo", "Endpoint / Comando", "Azioni"]
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        servers_layout.addWidget(self.table)

        table_bar = QHBoxLayout()
        self.add_stdio_btn = QPushButton("+ Aggiungi Server Locale (Stdio)")
        self.reload_btn = QPushButton("Ricarica")
        self.config_path_label = QLabel(f"File: {self.manager.config_path}")
        self.config_path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        table_bar.addWidget(self.add_stdio_btn)
        table_bar.addWidget(self.reload_btn)
        table_bar.addStretch(1)
        table_bar.addWidget(self.config_path_label)
        servers_layout.addLayout(table_bar)

        self.tabs.addTab(servers_tab, "Server MCP Installati")

        # Tab 2: Raw JSON Editor
        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        self.raw_editor = QPlainTextEdit()
        mono = QFont("Monospace")
        mono.setStyleHint(QFont.StyleHint.TypeWriter)
        self.raw_editor.setFont(mono)
        raw_layout.addWidget(self.raw_editor)

        raw_bar = QHBoxLayout()
        self.save_raw_btn = QPushButton("Valida e Salva JSON")
        self.format_raw_btn = QPushButton("Formatta JSON")
        self.reload_raw_btn = QPushButton("Ricarica da Disco")
        self.restore_bak_btn = QPushButton("Ripristina Backup (.bak)")
        raw_bar.addWidget(self.save_raw_btn)
        raw_bar.addWidget(self.format_raw_btn)
        raw_bar.addWidget(self.reload_raw_btn)
        raw_bar.addStretch(1)
        raw_bar.addWidget(self.restore_bak_btn)
        raw_layout.addLayout(raw_bar)

        self.tabs.addTab(raw_tab, "Editor JSON Raw")
        root_layout.addWidget(self.tabs, stretch=1)

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
        self.save_raw_btn.clicked.connect(self._save_raw_json)
        self.format_raw_btn.clicked.connect(self._format_raw_json)
        self.reload_raw_btn.clicked.connect(self.refresh_all)
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

    def _set_status(self, text: str, kind: str = "info") -> None:
        colors = {
            "info": "#60a5fa",
            "ok": "#10b981",
            "warn": "#f59e0b",
            "err": "#ef4444",
        }
        color = colors.get(kind, "#60a5fa")
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 500;")
        self.status_label.setText(text)

    def _toggle_advanced(self, expanded: bool) -> None:
        self.advanced_panel.setVisible(expanded)
        arrow = "▾" if expanded else "▸"
        self.advanced_toggle_btn.setText(
            f"{arrow} Opzioni Autenticazione & Bridge (Opzionale)"
        )

    def _paste_from_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            text = clipboard.text().strip()
            if text:
                self.url_input.setText(text)
            else:
                self._set_status("Gli appunti non contengono testo.", "warn")

    def _on_url_changed(self, text: str) -> None:
        stripped = text.strip()
        if not stripped:
            self._name_manually_edited = False
            self.name_input.clear()
            self.bridge_checkbox.setChecked(False)
            return

        if not self._name_manually_edited:
            self.name_input.setText(infer_server_name(stripped))

        if is_sse_url(stripped):
            self.bridge_checkbox.setChecked(True)
            self._set_status(
                "Rilevato endpoint /sse: abilitato automaticamente il bridge npx mcp-remote.",
                "warn",
            )

    def _on_name_edited(self, text: str) -> None:
        self._name_manually_edited = bool(text.strip())

    def _collect_quick_headers(self) -> dict[str, str]:
        mode = self.auth_combo.currentIndex()
        if mode == 0:
            return {}
        if mode == 1:
            token = self.bearer_input.text().strip()
            if not token:
                raise ValueError("Inserisci il Bearer token o seleziona 'Nessuna / OAuth'.")
            if token.lower().startswith("bearer "):
                token = token[7:].strip()
            return {"Authorization": f"Bearer {token}"}
        if mode == 2:
            hdr_name = self.apikey_header_input.text().strip()
            hdr_val = self.apikey_value_input.text().strip()
            if not hdr_name or not hdr_val:
                raise ValueError("Inserisci sia il nome dell'header che il valore API Key.")
            return {hdr_name: hdr_val}
        return parse_headers_text(self.custom_headers_input.toPlainText())

    def _start_probe(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            self._set_status("Inserisci un link MCP prima di testare la connessione.", "warn")
            return
        try:
            headers = self._collect_quick_headers()
        except ValueError as exc:
            self._set_status(str(exc), "err")
            return

        self.test_btn.setEnabled(False)
        self._set_status("Test connessione HTTP in corso...", "info")
        self._probe_worker = ProbeWorker(url, headers=headers, parent=self)
        self._probe_worker.finished_probe.connect(self._on_probe_finished)
        self._probe_worker.start()

    def _on_probe_finished(self, result: dict[str, Any]) -> None:
        self.test_btn.setEnabled(True)
        if result.get("is_legacy_sse"):
            self.bridge_checkbox.setChecked(True)
        if result.get("reachable"):
            kind = "warn" if result.get("needs_auth") else "ok"
            self._set_status(str(result.get("message", "Endpoint raggiungibile.")), kind)
        else:
            self._set_status(str(result.get("message", "Endpoint non raggiungibile.")), "err")

    def install_from_quick_bar(self, confirm_overwrite: bool = True) -> bool:
        """Validate quick-install inputs and write the remote server to mcp_config.json."""
        raw_url = self.url_input.text().strip()
        if not raw_url:
            self._set_status("Incolla prima il link del server MCP.", "err")
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
                f"Il server '{name}' esiste già nella configurazione.\nVuoi aggiornarlo con il nuovo URL?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        use_bridge = self.bridge_checkbox.isChecked()
        self.manager.add_remote_server(
            name=name,
            url=norm_url,
            headers=headers,
            use_bridge=use_bridge,
            disabled=False,
        )
        self.refresh_all()
        mode_desc = "tramite bridge npx mcp-remote" if use_bridge else "come HTTP remoto"
        self._set_status(
            f"Server '{name}' installato con successo ({mode_desc}) in Antigravity!",
            "ok",
        )
        return True

    def refresh_all(self) -> None:
        """Reload server table and raw JSON editor from disk."""
        try:
            servers = self.manager.get_servers()
            raw_text = self.manager.load_raw_text()
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Errore lettura mcp_config.json: {exc}", "err")
            return

        self.table.setRowCount(0)
        for row_idx, (name, entry) in enumerate(sorted(servers.items())):
            self.table.insertRow(row_idx)
            enabled = not bool(entry.get("disabled", False))

            # Col 0: Enable checkbox
            chk_container = QWidget()
            chk_layout = QHBoxLayout(chk_container)
            chk_layout.setContentsMargins(0, 0, 0, 0)
            chk_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            chk = QCheckBox()
            chk.setChecked(enabled)
            chk.toggled.connect(
                lambda state, srv=name: self._on_toggle_server(srv, state)
            )
            chk_layout.addWidget(chk)
            self.table.setCellWidget(row_idx, 0, chk_container)

            # Col 1: Name
            name_item = QTableWidgetItem(name)
            name_font = QFont()
            name_font.setBold(True)
            name_item.setFont(name_font)
            self.table.setItem(row_idx, 1, name_item)

            # Col 2: Type badge
            kind = MCPConfigManager.classify_server(entry)
            kind_labels = {
                "remote": "HTTP REMOTO",
                "bridge": "BRIDGE SSE",
                "stdio": "STDIO LOCALE",
            }
            kind_item = QTableWidgetItem(kind_labels.get(kind, kind.upper()))
            self.table.setItem(row_idx, 2, kind_item)

            # Col 3: Endpoint / command summary (secrets redacted)
            endpoint = MCPConfigManager.get_server_endpoint(entry)
            secret_tag = MCPConfigManager.summarize_secrets_count(entry)
            endpoint_item = QTableWidgetItem(f"{endpoint}{secret_tag}")
            self.table.setItem(row_idx, 3, endpoint_item)

            # Col 4: Actions
            actions_widget = QWidget()
            actions_layout = QHBoxLayout(actions_widget)
            actions_layout.setContentsMargins(4, 2, 4, 2)
            actions_layout.setSpacing(6)
            edit_btn = QPushButton("Modifica")
            del_btn = QPushButton("Elimina")
            edit_btn.clicked.connect(
                lambda _checked=False, srv=name, ent=entry: self._edit_server(srv, ent)
            )
            del_btn.clicked.connect(
                lambda _checked=False, srv=name: self._delete_server(srv)
            )
            actions_layout.addWidget(edit_btn)
            actions_layout.addWidget(del_btn)
            self.table.setCellWidget(row_idx, 4, actions_widget)

        self.raw_editor.setPlainText(raw_text)
        self.restore_bak_btn.setEnabled(self.manager.backup_path.exists())

    def _on_toggle_server(self, name: str, enabled: bool) -> None:
        try:
            self.manager.set_server_enabled(name, enabled)
            state_txt = "attivato" if enabled else "disattivato"
            self._set_status(f"Server '{name}' {state_txt}.", "info")
            self.raw_editor.setPlainText(self.manager.load_raw_text())
            self.restore_bak_btn.setEnabled(self.manager.backup_path.exists())
        except Exception as exc:  # noqa: BLE001
            self._set_status(f"Errore aggiornamento '{name}': {exc}", "err")
            self.refresh_all()

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
                self._set_status(f"Server '{name}' salvato.", "ok")

    def _edit_server(self, name: str, entry: dict[str, Any]) -> None:
        dialog = ServerEditDialog(parent=self, name=name, entry=entry)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            result = dialog.get_result()
            if result is not None:
                srv_name, new_entry = result
                self.manager.set_server_entry(srv_name, new_entry)
                self.refresh_all()
                self._set_status(f"Server '{srv_name}' aggiornato.", "ok")

    def _delete_server(self, name: str) -> None:
        reply = QMessageBox.question(
            self,
            "Conferma eliminazione",
            f"Vuoi rimuovere il server MCP '{name}' dalla configurazione di Antigravity?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.manager.remove_server(name):
            self.refresh_all()
            self._set_status(f"Server '{name}' rimosso.", "info")

    def _format_raw_json(self) -> None:
        try:
            parsed = json.loads(self.raw_editor.toPlainText())
            self.raw_editor.setPlainText(
                json.dumps(parsed, indent=2, ensure_ascii=False) + "\n"
            )
            self._set_status("JSON formattato correttamente.", "info")
        except json.JSONDecodeError as exc:
            QMessageBox.warning(self, "JSON non valido", f"Errore di sintassi JSON:\n{exc}")

    def _save_raw_json(self) -> None:
        try:
            self.manager.save_raw_text(self.raw_editor.toPlainText())
            self.refresh_all()
            self._set_status("Configurazione JSON salvata con backup automatico.", "ok")
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, "Errore salvataggio JSON", str(exc))

    def _restore_backup(self) -> None:
        if not self.manager.backup_path.exists():
            self._set_status("Nessun file di backup (.bak) trovato.", "warn")
            return
        reply = QMessageBox.question(
            self,
            "Ripristina backup",
            f"Vuoi ripristinare {self.manager.config_path.name} dall'ultimo backup (.bak)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if self.manager.restore_backup():
                self.refresh_all()
                self._set_status("Configurazione ripristinata dal backup (.bak).", "ok")
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
            self._set_status("Controllo nuove versioni su GitHub in corso...", "info")
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
                self._set_status(
                    f"agymcp v{info.current_version} è già aggiornato all'ultima versione.",
                    "ok",
                )
            return

        self._pending_update = info
        self.update_banner.setVisible(True)
        self.restart_app_btn.setVisible(False)
        if self.auto_update_checkbox.isChecked():
            self.update_now_btn.setVisible(False)
            self.update_banner_label.setText(
                f"Nuova versione v{info.latest_version} rilevata! "
                "Download e installazione automatica in corso..."
            )
            self._start_update_install()
        else:
            self.update_now_btn.setVisible(True)
            self.update_banner_label.setText(
                f"Nuova versione v{info.latest_version} disponibile "
                f"(attuale: v{info.current_version})."
            )

    def _start_update_install(self) -> None:
        if self._pending_update is None:
            return
        if self._update_install_worker is not None and self._update_install_worker.isRunning():
            return
        self.update_now_btn.setEnabled(False)
        self.update_banner_label.setText(
            f"Installazione aggiornamento v{self._pending_update.latest_version} in corso..."
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
            self.update_now_btn.setVisible(False)
            self.restart_app_btn.setVisible(result.restart_required)
            self.update_banner_label.setText(
                f"{result.message} Clicca 'Riavvia agymcp' per usare subito la v{result.new_version}."
            )
            self._set_status(result.message, "ok")
        else:
            self.update_now_btn.setVisible(True)
            self.update_banner_label.setText(result.message)
            self._set_status(result.message, "err")

    def _restart_application(self) -> None:
        launcher = Path.home() / ".local" / "bin" / "agymcp"
        if launcher.exists() and os.access(launcher, os.X_OK):
            os.execv(str(launcher), [str(launcher)])
        os.execv(sys.executable, [sys.executable, "-m", "agymcp.cli"])


def launch_gui(
    manager: MCPConfigManager | None = None,
    initial_url: str = "",
) -> int:
    """Launch the PyQt6 desktop application."""
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("agymcp")
    window = MainWindow(manager=manager, initial_url=initial_url)
    window.show()
    return app.exec()
