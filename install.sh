#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="/usr/bin/python3"

if ! "${PYTHON_BIN}" -c "import PyQt6" >/dev/null 2>&1; then
  echo "Errore: PyQt6 non trovato in ${PYTHON_BIN}." >&2
  echo "Installa PyQt6 (Fedora: 'sudo dnf install python3-pyqt6', Debian/Ubuntu: 'sudo apt install python3-pyqt6') e riprova." >&2
  exit 1
fi

BIN_DIR="${HOME}/.local/bin"
HICOLOR_DIR="${HOME}/.local/share/icons/hicolor"
ICON_DIR="${HICOLOR_DIR}/scalable/apps"
PIXMAPS_DIR="${HOME}/.local/share/pixmaps"
APP_DIR="${HOME}/.local/share/applications"

mkdir -p "${BIN_DIR}" "${ICON_DIR}" "${PIXMAPS_DIR}" "${APP_DIR}"

LAUNCHER_PATH="${BIN_DIR}/agymcp"
cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${PROJECT_DIR}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec "${PYTHON_BIN}" -m agymcp.cli "\$@"
EOF
chmod +x "${LAUNCHER_PATH}"

cp "${PROJECT_DIR}/assets/agymcp.svg" "${ICON_DIR}/agymcp.svg"
cp "${PROJECT_DIR}/assets/agymcp.svg" "${PIXMAPS_DIR}/agymcp.svg"

DESKTOP_PATH="${APP_DIR}/agymcp.desktop"
sed "s|^Exec=.*|Exec=${LAUNCHER_PATH}|" "${PROJECT_DIR}/assets/agymcp.desktop" > "${DESKTOP_PATH}"
chmod 0644 "${DESKTOP_PATH}"

# Refresh desktop menus & icon caches across KDE Plasma 6/5, GNOME, XFCE, Cinnamon, Wayland
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${APP_DIR}" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -t "${HICOLOR_DIR}" >/dev/null 2>&1 || true
fi
if command -v xdg-desktop-menu >/dev/null 2>&1; then
  xdg-desktop-menu forceupdate >/dev/null 2>&1 || true
fi
if command -v kbuildsycoca6 >/dev/null 2>&1; then
  kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
elif command -v kbuildsycoca5 >/dev/null 2>&1; then
  kbuildsycoca5 --noincremental >/dev/null 2>&1 || true
fi

echo "Installazione completata:"
echo "  CLI / Launcher : ${LAUNCHER_PATH}"
echo "  Icona          : ${ICON_DIR}/agymcp.svg"
echo "  App Desktop    : ${DESKTOP_PATH} (menu KDE/GNOME/XFCE aggiornato)"
echo
echo "Avvia la GUI dal menu applicazioni ('agymcp') oppure con: agymcp"
echo "Installa un link con OAuth da terminale: agymcp https://api.streak.com/mcp --auth"
