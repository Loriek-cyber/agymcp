"""Automated GitHub Releases updater for agymcp."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agymcp import __version__

DEFAULT_REPO = "Loriek-cyber/agymcp"
SETTINGS_PATH = Path.home() / ".config" / "agymcp" / "settings.json"
STANDALONE_INSTALL_DIR = Path.home() / ".local" / "share" / "agymcp" / "app"

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


@dataclass(frozen=True)
class UpdateInfo:
    """Result of checking GitHub Releases for a newer version."""

    current_version: str
    latest_version: str
    update_available: bool
    release_url: str = ""
    download_url: str = ""
    release_notes: str = ""
    error: str = ""


@dataclass(frozen=True)
class UpdateResult:
    """Outcome of downloading and installing an update."""

    success: bool
    new_version: str
    method: str
    message: str
    restart_required: bool = False


def parse_version(version_str: str) -> tuple[int, int, int]:
    """Parse 'vX.Y.Z' or 'X.Y.Z' into (major, minor, patch)."""
    match = _SEMVER_RE.match(version_str.strip())
    if not match:
        raise ValueError(f"Formato versione non valido: {version_str!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def is_newer_version(latest: str, current: str) -> bool:
    """Return True when latest > current according to semantic versioning."""
    return parse_version(latest) > parse_version(current)


def load_settings(settings_path: Path = SETTINGS_PATH) -> dict[str, Any]:
    """Load persisted updater preferences (default: auto_update enabled)."""
    defaults: dict[str, Any] = {"auto_update": True}
    if not settings_path.exists():
        return defaults
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            defaults.update(data)
    except Exception:  # noqa: BLE001
        pass
    return defaults


def save_settings(settings: dict[str, Any], settings_path: Path = SETTINGS_PATH) -> None:
    """Persist updater preferences."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _select_download_url(release_data: dict[str, Any]) -> str:
    """Pick the best tarball asset from a GitHub Release payload."""
    assets = release_data.get("assets") or []
    for asset in assets:
        name = str(asset.get("name", ""))
        dl = str(asset.get("browser_download_url", ""))
        if name.startswith("agymcp-") and name.endswith(".tar.gz") and dl:
            return dl
    return str(release_data.get("tarball_url", ""))


def check_for_updates(
    current_version: str = __version__,
    repo: str = DEFAULT_REPO,
    timeout: float = 6.0,
) -> UpdateInfo:
    """Query GitHub Releases API to check whether a newer agymcp version exists."""
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"agymcp/{current_version}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return UpdateInfo(
                current_version=current_version,
                latest_version=current_version,
                update_available=False,
                error="Nessuna release pubblicata su GitHub al momento.",
            )
        return UpdateInfo(
            current_version=current_version,
            latest_version=current_version,
            update_available=False,
            error=f"Errore GitHub API (HTTP {exc.code}).",
        )
    except Exception as exc:  # noqa: BLE001
        return UpdateInfo(
            current_version=current_version,
            latest_version=current_version,
            update_available=False,
            error=f"Impossibile verificare aggiornamenti: {exc}",
        )

    tag = str(payload.get("tag_name") or "").strip()
    if not tag:
        return UpdateInfo(
            current_version=current_version,
            latest_version=current_version,
            update_available=False,
            error="La risposta GitHub non contiene tag_name.",
        )

    latest_clean = tag.lstrip("v")
    try:
        newer = is_newer_version(latest_clean, current_version)
    except ValueError as exc:
        return UpdateInfo(
            current_version=current_version,
            latest_version=latest_clean,
            update_available=False,
            error=str(exc),
        )

    return UpdateInfo(
        current_version=current_version,
        latest_version=latest_clean,
        update_available=newer,
        release_url=str(payload.get("html_url", "")),
        download_url=_select_download_url(payload),
        release_notes=str(payload.get("body", "") or "").strip(),
    )


def _is_clean_git_repo(project_dir: Path) -> bool:
    if not (project_dir / ".git").exists():
        return False
    try:
        status = subprocess.run(
            ["git", "-C", str(project_dir), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return status.stdout.strip() == ""
    except Exception:  # noqa: BLE001
        return False


def _safe_extract_tar(tar_path: Path, dest_dir: Path) -> Path:
    """Safely extract a .tar.gz archive preventing path traversal and return root dir."""
    dest_resolved = dest_dir.resolve()
    with tarfile.open(tar_path, "r:gz") as tar:
        for member in tar.getmembers():
            target = (dest_dir / member.name).resolve()
            if not str(target).startswith(str(dest_resolved) + os.sep) and target != dest_resolved:
                raise ValueError(f"Percorso non sicuro nell'archivio: {member.name}")
        tar.extractall(dest_dir)

    # Locate the directory containing install.sh or agymcp/
    if (dest_dir / "install.sh").exists() or (dest_dir / "agymcp").is_dir():
        return dest_dir
    subdirs = [p for p in dest_dir.iterdir() if p.is_dir()]
    if len(subdirs) == 1:
        return subdirs[0]
    raise RuntimeError("Struttura archivio release non riconosciuta.")


def _run_install_script(app_dir: Path) -> None:
    install_sh = app_dir / "install.sh"
    if not install_sh.exists():
        raise FileNotFoundError(f"install.sh non trovato in {app_dir}")
    install_sh.chmod(0o755)
    subprocess.run(
        ["bash", str(install_sh)],
        cwd=str(app_dir),
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def apply_update(
    info: UpdateInfo,
    project_dir: Path | None = None,
    install_dir: Path = STANDALONE_INSTALL_DIR,
    timeout: float = 30.0,
) -> UpdateResult:
    """Download and install the latest release either via git pull or release tarball."""
    if not info.update_available:
        return UpdateResult(
            success=True,
            new_version=info.current_version,
            method="none",
            message=f"agymcp è già aggiornato alla versione {info.current_version}.",
            restart_required=False,
        )

    repo_dir = project_dir or Path(__file__).resolve().parent.parent

    # Method 1: Clean local git clone -> pull latest main & re-run install.sh
    if _is_clean_git_repo(repo_dir):
        try:
            subprocess.run(
                ["git", "-C", str(repo_dir), "fetch", "--tags", "origin"],
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
            )
            subprocess.run(
                ["git", "-C", str(repo_dir), "pull", "--ff-only", "origin", "main"],
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
            )
            _run_install_script(repo_dir)
            return UpdateResult(
                success=True,
                new_version=info.latest_version,
                method="git",
                message=(
                    f"Aggiornamento v{info.latest_version} scaricato via git e "
                    "installato automaticamente."
                ),
                restart_required=True,
            )
        except Exception:  # noqa: BLE001
            # Fall back to downloading the GitHub Release tarball
            pass

    # Method 2: Download release tarball and install to ~/.local/share/agymcp/app
    if not info.download_url:
        return UpdateResult(
            success=False,
            new_version=info.current_version,
            method="tarball",
            message="Nessun URL di download disponibile nella release GitHub.",
            restart_required=False,
        )

    try:
        with tempfile.TemporaryDirectory(prefix="agymcp-update-") as tmp:
            tmp_path = Path(tmp)
            archive_path = tmp_path / f"agymcp-{info.latest_version}.tar.gz"
            req = urllib.request.Request(
                info.download_url,
                headers={"User-Agent": f"agymcp/{info.current_version}"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                archive_path.write_bytes(resp.read())

            extract_dir = tmp_path / "extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            source_root = _safe_extract_tar(archive_path, extract_dir)

            install_dir.parent.mkdir(parents=True, exist_ok=True)
            staging_dir = install_dir.with_name(f"{install_dir.name}.new")
            if staging_dir.exists():
                shutil.rmtree(staging_dir)
            shutil.copytree(source_root, staging_dir)

            old_dir = install_dir.with_name(f"{install_dir.name}.old")
            if old_dir.exists():
                shutil.rmtree(old_dir)
            if install_dir.exists():
                install_dir.rename(old_dir)
            staging_dir.rename(install_dir)
            if old_dir.exists():
                shutil.rmtree(old_dir)

            _run_install_script(install_dir)
            return UpdateResult(
                success=True,
                new_version=info.latest_version,
                method="tarball",
                message=(
                    f"Versione v{info.latest_version} scaricata e installata in "
                    f"{install_dir}."
                ),
                restart_required=True,
            )
    except Exception as exc:  # noqa: BLE001
        return UpdateResult(
            success=False,
            new_version=info.current_version,
            method="tarball",
            message=f"Aggiornamento fallito: {exc}",
            restart_required=False,
        )
