"""Unit, CLI, and offscreen GUI tests for agymcp."""

from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from agymcp.cli import main as cli_main
from agymcp.core import (
    MCPConfigManager,
    infer_server_name,
    is_sse_url,
    normalize_url,
    parse_env_text,
    parse_headers_text,
)


class TestUrlAndParsing(unittest.TestCase):
    def test_infer_server_name_examples(self) -> None:
        cases = {
            "https://api.streak.com/mcp": "streak",
            "https://mcp.cloudflare.com/mcp": "cloudflare",
            "https://mcp.figma.com/mcp": "figma",
            "https://stitch.googleapis.com/mcp": "stitch",
            "https://zprojects.zohomcp.com/mcp/message": "zprojects-zohomcp",
            "https://mcp.com/mcp": "mcp",
            "http://localhost:8080/mcp": "localhost",
            "api.streak.com/mcp": "streak",
        }
        for url, expected in cases.items():
            with self.subTest(url=url):
                self.assertEqual(infer_server_name(url), expected)

    def test_normalize_url(self) -> None:
        self.assertEqual(
            normalize_url("api.streak.com/mcp"),
            "https://api.streak.com/mcp",
        )
        self.assertEqual(
            normalize_url("  https://api.streak.com/mcp  "),
            "https://api.streak.com/mcp",
        )
        with self.assertRaises(ValueError):
            normalize_url("   ")
        with self.assertRaises(ValueError):
            normalize_url("ftp://example.com/mcp")

    def test_is_sse_url(self) -> None:
        self.assertTrue(is_sse_url("https://example.com/sse"))
        self.assertTrue(is_sse_url("https://example.com/v1/sse/"))
        self.assertFalse(is_sse_url("https://api.streak.com/mcp"))

    def test_parse_headers_and_env(self) -> None:
        headers = parse_headers_text("Authorization: Bearer abc\n# comment\nX-Key: 123\n")
        self.assertEqual(headers, {"Authorization": "Bearer abc", "X-Key": "123"})
        with self.assertRaises(ValueError):
            parse_headers_text("InvalidHeaderLine")

        env = parse_env_text("API_KEY=secret=val\nDEBUG=1\n")
        self.assertEqual(env, {"API_KEY": "secret=val", "DEBUG": "1"})
        with self.assertRaises(ValueError):
            parse_env_text("MISSING_EQUALS")


class TestMCPConfigManager(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp_dir.name) / "mcp_config.json"
        self.manager = MCPConfigManager(self.cfg_path)

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_add_remote_native_and_headers(self) -> None:
        self.manager.add_remote_server(
            name="streak",
            url="https://api.streak.com/mcp",
        )
        data = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        self.assertEqual(
            data["mcpServers"]["streak"],
            {"serverUrl": "https://api.streak.com/mcp", "disabled": False},
        )

        # Updating creates .bak and preserves previous state in backup
        self.manager.add_remote_server(
            name="custom",
            url="https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer tok123"},
        )
        self.assertTrue(self.manager.backup_path.exists())
        data2 = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        self.assertIn("streak", data2["mcpServers"])
        self.assertEqual(
            data2["mcpServers"]["custom"],
            {
                "serverUrl": "https://mcp.example.com/mcp",
                "disabled": False,
                "headers": {"Authorization": "Bearer tok123"},
            },
        )
        self.assertEqual(self.manager.classify_server(data2["mcpServers"]["custom"]), "remote")
        self.assertNotIn(
            "tok123",
            MCPConfigManager.summarize_secrets_count(data2["mcpServers"]["custom"]),
        )

        # Restore backup removes 'custom' and brings back previous file
        self.assertTrue(self.manager.restore_backup())
        restored = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        self.assertIn("streak", restored["mcpServers"])
        self.assertNotIn("custom", restored["mcpServers"])

    def test_add_bridge_and_stdio_and_toggle_remove(self) -> None:
        self.manager.add_remote_server(
            name="legacy-sse",
            url="https://old.example.com/sse",
            headers={"X-Api-Key": "k1"},
            use_bridge=True,
        )
        self.manager.add_stdio_server(
            name="markitdown",
            command="uvx",
            args=["markitdown-mcp"],
            env={"PYTHONUNBUFFERED": "1"},
        )
        servers = self.manager.get_servers()
        self.assertEqual(self.manager.classify_server(servers["legacy-sse"]), "bridge")
        self.assertEqual(
            servers["legacy-sse"]["args"],
            ["-y", "mcp-remote", "https://old.example.com/sse", "--header", "X-Api-Key: k1"],
        )
        self.assertEqual(self.manager.classify_server(servers["markitdown"]), "stdio")
        self.assertEqual(servers["markitdown"]["env"], {"PYTHONUNBUFFERED": "1"})

        self.manager.set_server_enabled("markitdown", False)
        self.assertTrue(self.manager.get_servers()["markitdown"]["disabled"])

        self.manager.set_server_enabled("markitdown", True)
        self.assertFalse(self.manager.get_servers()["markitdown"]["disabled"])

        self.assertTrue(self.manager.remove_server("legacy-sse"))
        self.assertNotIn("legacy-sse", self.manager.get_servers())
        self.assertFalse(self.manager.remove_server("does-not-exist"))


class TestCLIAndOffscreenGUI(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp_dir.name) / "mcp_config.json"

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_cli_install_list_toggle_remove(self) -> None:
        secret = "super-secret-token-value"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli_main(
                [
                    "https://api.streak.com/mcp",
                    "--bearer",
                    secret,
                    "--config",
                    str(self.cfg_path),
                ]
            )
        self.assertEqual(rc, 0)
        self.assertIn("Installato 'streak'", buf.getvalue())

        list_buf = io.StringIO()
        with contextlib.redirect_stdout(list_buf):
            rc = cli_main(["--list", "--config", str(self.cfg_path)])
        self.assertEqual(rc, 0)
        output = list_buf.getvalue()
        self.assertIn("streak", output)
        self.assertIn("https://api.streak.com/mcp", output)
        self.assertNotIn(secret, output)

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                cli_main(["--disable", "streak", "--config", str(self.cfg_path)]),
                0,
            )
        self.assertTrue(MCPConfigManager(self.cfg_path).get_servers()["streak"]["disabled"])

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                cli_main(["--enable", "streak", "--config", str(self.cfg_path)]),
                0,
            )
        self.assertFalse(MCPConfigManager(self.cfg_path).get_servers()["streak"]["disabled"])

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                cli_main(["--remove", "streak", "--config", str(self.cfg_path)]),
                0,
            )
        self.assertNotIn("streak", MCPConfigManager(self.cfg_path).get_servers())

    def test_offscreen_gui_quick_install(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        from agymcp.gui import MainWindow

        app = QApplication.instance() or QApplication([])
        manager = MCPConfigManager(self.cfg_path)
        window = MainWindow(manager=manager)

        window.url_input.setText("https://example.com/sse")
        self.assertTrue(window.bridge_checkbox.isChecked())

        window.url_input.setText("")
        window.url_input.setText("https://api.streak.com/mcp")
        self.assertEqual(window.name_input.text(), "streak")
        self.assertFalse(window.bridge_checkbox.isChecked())

        ok = window.install_from_quick_bar(confirm_overwrite=False)
        self.assertTrue(ok)
        servers = manager.get_servers()
        self.assertIn("streak", servers)
        self.assertEqual(servers["streak"]["serverUrl"], "https://api.streak.com/mcp")
        self.assertEqual(window.table.rowCount(), 1)
        window.close()
        app.processEvents()


if __name__ == "__main__":
    unittest.main()
