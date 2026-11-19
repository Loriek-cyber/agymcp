#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('${PROJECT_DIR}/agymcp/__init__.py').read()).group(1))")}"
OUT_DIR="${2:-${PROJECT_DIR}/dist}"

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "Errore: 'dpkg-deb' non trovato. Installa 'dpkg' per generare il pacchetto .deb." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

PKG_ROOT="${WORK_DIR}/agymcp_${VERSION}-1_all"
mkdir -p \
  "${PKG_ROOT}/DEBIAN" \
  "${PKG_ROOT}/usr/bin" \
  "${PKG_ROOT}/usr/share/agymcp" \
  "${PKG_ROOT}/usr/share/applications" \
  "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps" \
  "${PKG_ROOT}/usr/share/pixmaps"

cp -r "${PROJECT_DIR}/agymcp" "${PROJECT_DIR}/assets" "${PROJECT_DIR}/README.md" "${PROJECT_DIR}/pyproject.toml" "${PKG_ROOT}/usr/share/agymcp/"

cat > "${PKG_ROOT}/usr/bin/agymcp" <<'EOF'
#!/usr/bin/env bash
export PYTHONPATH="/usr/share/agymcp${PYTHONPATH:+:${PYTHONPATH}}"
exec /usr/bin/python3 -m agymcp.cli "$@"
EOF
chmod 0755 "${PKG_ROOT}/usr/bin/agymcp"

cp "${PROJECT_DIR}/assets/agymcp.svg" "${PKG_ROOT}/usr/share/icons/hicolor/scalable/apps/agymcp.svg"
cp "${PROJECT_DIR}/assets/agymcp.svg" "${PKG_ROOT}/usr/share/pixmaps/agymcp.svg"
sed 's|^Exec=.*|Exec=/usr/bin/agymcp|' "${PROJECT_DIR}/assets/agymcp.desktop" > "${PKG_ROOT}/usr/share/applications/agymcp.desktop"
chmod 0644 "${PKG_ROOT}/usr/share/applications/agymcp.desktop"

cat > "${PKG_ROOT}/DEBIAN/control" <<EOF
Package: agymcp
Version: ${VERSION}-1
Section: devel
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-pyqt6
Maintainer: Loriek-cyber <loriek@users.noreply.github.com>
Homepage: https://github.com/Loriek-cyber/agymcp
Description: Antigravity MCP Installer & Manager
 Native PyQt6 desktop app and CLI utility to install, authenticate (OAuth 2.1 + PKCE),
 and manage Model Context Protocol (MCP) servers on Google Antigravity.
EOF

cat > "${PKG_ROOT}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
fi
EOF
chmod 0755 "${PKG_ROOT}/DEBIAN/postinst"

cat > "${PKG_ROOT}/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q -f -t /usr/share/icons/hicolor || true
fi
EOF
chmod 0755 "${PKG_ROOT}/DEBIAN/postrm"

DEST_DEB="${OUT_DIR}/agymcp_${VERSION}-1_all.deb"
dpkg-deb --build --root-owner-group "${PKG_ROOT}" "${DEST_DEB}"
echo "Pacchetto Debian/Ubuntu DEB creato: ${DEST_DEB}"
