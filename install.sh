#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="/usr/bin/python3"

if ! "${PYTHON_BIN}" -c "import PyQt6" >/dev/null 2>&1; then
  echo "Errore: PyQt6 non trovato in ${PYTHON_BIN}." >&2
  echo "Installa PyQt6 (es. 'pip install PyQt6' o pacchetto di sistema python-pyqt6) e riprova." >&2
  exit 1
fi

BIN_DIR="${HOME}/.local/bin"
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
APP_DIR="${HOME}/.local/share/applications"

mkdir -p "${BIN_DIR}" "${ICON_DIR}" "${APP_DIR}"

LAUNCHER_PATH="${BIN_DIR}/agymcp"
cat > "${LAUNCHER_PATH}" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${PROJECT_DIR}\${PYTHONPATH:+:\${PYTHONPATH}}"
exec "${PYTHON_BIN}" -m agymcp.cli "\$@"
EOF
chmod +x "${LAUNCHER_PATH}"

cp "${PROJECT_DIR}/assets/agymcp.svg" "${ICON_DIR}/agymcp.svg"

DESKTOP_PATH="${APP_DIR}/agymcp.desktop"
sed "s|^Exec=.*|Exec=${LAUNCHER_PATH}|" "${PROJECT_DIR}/assets/agymcp.desktop" > "${DESKTOP_PATH}"

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${APP_DIR}" >/dev/null 2>&1 || true
fi

echo "Installazione completata:"
echo "  CLI / Launcher : ${LAUNCHER_PATH}"
echo "  Icona          : ${ICON_DIR}/agymcp.svg"
echo "  App Desktop    : ${DESKTOP_PATH}"
echo
echo "Avvia la GUI con: agymcp"
echo "Oppure installa un link da terminale con: agymcp https://api.streak.com/mcp"
