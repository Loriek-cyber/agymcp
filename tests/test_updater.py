"""Tests for the 3-tier version bumper and GitHub Release auto-updater."""

from __future__ import annotations

import tarfile
import tempfile
import unittest
from pathlib import Path

from agymcp.updater import (
    UpdateInfo,
    _safe_extract_tar,
    is_newer_version,
    load_settings,
    parse_version,
    save_settings,
)
from scripts.bump_version import (
    bump_version,
    detect_bump_level,
    read_current_version,
    write_new_version,
)


class TestThreeTierVersioning(unittest.TestCase):
    def test_detect_bump_level_three_tiers(self) -> None:
        # Tier 1: Patch -> X.Y.(Z+1)
        self.assertEqual(detect_bump_level("[patch] fix typo in tooltip"), "patch")
        self.assertEqual(detect_bump_level("[fix] handle empty header"), "patch")
        self.assertEqual(detect_bump_level("fix(gui): prevent crash"), "patch")

        # Tier 2: Minor -> X.(Y+1).0
        self.assertEqual(detect_bump_level("[minor] add OAuth status badge"), "minor")
        self.assertEqual(detect_bump_level("[feat] add auto-updater"), "minor")
        self.assertEqual(detect_bump_level("feat(cli): add --update flag"), "minor")

        # Tier 3: Major -> (X+1).0.0
        self.assertEqual(detect_bump_level("[major] new config format"), "major")
        self.assertEqual(detect_bump_level("[breaking] drop old flag"), "major")
        self.assertEqual(detect_bump_level("feat!: rewrite storage"), "major")
        self.assertEqual(
            detect_bump_level("[patch] small change\n\nBREAKING CHANGE: schema v2"),
            "major",
        )

        # Skip release cases
        self.assertIsNone(detect_bump_level("chore(release): v0.1.1 [skip ci]"))
        self.assertIsNone(detect_bump_level("[no-release] update notes"))
        self.assertIsNone(detect_bump_level("random commit without tag"))

    def test_bump_version_math(self) -> None:
        self.assertEqual(bump_version("1.0.1", "patch"), "1.0.2")
        self.assertEqual(bump_version("1.0.1", "minor"), "1.1.0")
        self.assertEqual(bump_version("1.1.1", "major"), "2.0.0")

    def test_write_and_read_version_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            init_file = tmp_path / "__init__.py"
            pyproject_file = tmp_path / "pyproject.toml"
            init_file.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
            pyproject_file.write_text(
                '[project]\nname = "agymcp"\nversion = "1.0.0"\n',
                encoding="utf-8",
            )

            self.assertEqual(read_current_version(init_file), "1.0.0")
            write_new_version("1.2.3", init_file=init_file, pyproject_file=pyproject_file)
            self.assertEqual(read_current_version(init_file), "1.2.3")
            self.assertIn('version = "1.2.3"', pyproject_file.read_text(encoding="utf-8"))


class TestUpdaterHelpers(unittest.TestCase):
    def test_version_comparison(self) -> None:
        self.assertEqual(parse_version("v1.2.3"), (1, 2, 3))
        self.assertTrue(is_newer_version("v0.2.0", "0.1.0"))
        self.assertTrue(is_newer_version("1.0.0", "0.9.9"))
        self.assertFalse(is_newer_version("0.1.0", "0.1.0"))
        self.assertFalse(is_newer_version("0.0.9", "0.1.0"))

    def test_settings_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            self.assertTrue(load_settings(settings_path)["auto_update"])
            save_settings({"auto_update": False}, settings_path)
            self.assertFalse(load_settings(settings_path)["auto_update"])

    def test_safe_extract_tar(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src_dir = tmp_path / "agymcp-v0.2.0"
            (src_dir / "agymcp").mkdir(parents=True)
            (src_dir / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")

            archive = tmp_path / "agymcp-v0.2.0.tar.gz"
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(src_dir, arcname="agymcp-v0.2.0")

            out_dir = tmp_path / "out"
            out_dir.mkdir()
            extracted_root = _safe_extract_tar(archive, out_dir)
            self.assertTrue((extracted_root / "install.sh").exists())

            # Verify UpdateInfo dataclass fields
            info = UpdateInfo("0.1.0", "0.2.0", True)
            self.assertTrue(info.update_available)


if __name__ == "__main__":
    unittest.main()
