#!/usr/bin/env python3
"""Automatic 3-tier semantic version bumper driven by commit tags.

Supported commit message prefixes (case-insensitive):
  - [major] / [breaking] / BREAKING CHANGE / type!:  -> (X+1).0.0
  - [minor] / [feat]     / feat:                     -> X.(Y+1).0
  - [patch] / [fix]      / fix:                      -> X.Y.(Z+1)
  - [no-release] / [skip ci] / chore(release):       -> no bump
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
INIT_FILE = ROOT_DIR / "agymcp" / "__init__.py"
PYPROJECT_FILE = ROOT_DIR / "pyproject.toml"

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse 'X.Y.Z' or 'vX.Y.Z' into a 3-tuple of ints."""
    match = _VERSION_RE.match(version_str.strip())
    if not match:
        raise ValueError(f"Versione non valida: {version_str!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def detect_bump_level(commit_message: str) -> str | None:
    """Detect 'major', 'minor', 'patch', or None from a commit message."""
    msg = commit_message.strip()
    if not msg:
        return None

    lower = msg.lower()
    first_line = msg.splitlines()[0].strip()
    first_lower = first_line.lower()

    # Never re-trigger on release commits or explicit skip markers
    if (
        "[skip ci]" in lower
        or "[no-release]" in lower
        or first_lower.startswith("chore(release):")
    ):
        return None

    # Tier 3: Major -> (X+1).0.0
    if (
        "[major]" in first_lower
        or "[breaking]" in first_lower
        or "breaking change" in lower
        or re.match(r"^[a-z]+(\([^)]+\))?!:", first_lower)
    ):
        return "major"

    # Tier 2: Minor -> X.(Y+1).0
    if (
        "[minor]" in first_lower
        or "[feat]" in first_lower
        or re.match(r"^feat(\([^)]+\))?:", first_lower)
    ):
        return "minor"

    # Tier 1: Patch -> X.Y.(Z+1)
    if (
        "[patch]" in first_lower
        or "[fix]" in first_lower
        or re.match(r"^(fix|perf|refactor|docs|chore|style|test)(\([^)]+\))?:", first_lower)
    ):
        return "patch"

    return None


def bump_version(current: str, level: str) -> str:
    """Compute the next semantic version string for the given bump level."""
    major, minor, patch = parse_version(current)
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    if level == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Livello bump non supportato: {level!r}")


def read_current_version(init_file: Path = INIT_FILE) -> str:
    """Read __version__ from agymcp/__init__.py."""
    content = init_file.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', content)
    if not match:
        raise RuntimeError(f"Impossibile trovare __version__ in {init_file}")
    return match.group(1)


def write_new_version(
    new_version: str,
    init_file: Path = INIT_FILE,
    pyproject_file: Path = PYPROJECT_FILE,
) -> None:
    """Update version strings in agymcp/__init__.py and pyproject.toml."""
    init_text = init_file.read_text(encoding="utf-8")
    updated_init, init_count = re.subn(
        r'(__version__\s*=\s*")([^"]+)(")',
        rf"\g<1>{new_version}\g<3>",
        init_text,
        count=1,
    )
    if init_count != 1:
        raise RuntimeError(f"Impossibile aggiornare __version__ in {init_file}")
    init_file.write_text(updated_init, encoding="utf-8")

    pyproject_text = pyproject_file.read_text(encoding="utf-8")
    updated_pyproject, py_count = re.subn(
        r'(^version\s*=\s*")([^"]+)(")',
        rf"\g<1>{new_version}\g<3>",
        pyproject_text,
        count=1,
        flags=re.MULTILINE,
    )
    if py_count != 1:
        raise RuntimeError(f"Impossibile aggiornare version in {pyproject_file}")
    pyproject_file.write_text(updated_pyproject, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump agymcp semantic version.")
    parser.add_argument(
        "--message",
        default="",
        help="Messaggio di commit da analizzare per il bump automatico",
    )
    parser.add_argument(
        "--level",
        choices=["auto", "patch", "minor", "major"],
        default="auto",
        help="Forza un livello di bump o usa 'auto' dal messaggio di commit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcola e stampa la nuova versione senza modificare i file",
    )
    args = parser.parse_args(argv)

    current = read_current_version()
    level = detect_bump_level(args.message) if args.level == "auto" else args.level
    if not level:
        print("NO_BUMP")
        return 0

    new_version = bump_version(current, level)
    if not args.dry_run:
        write_new_version(new_version)
    print(new_version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
