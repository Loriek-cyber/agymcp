#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VERSION="${1:-$(python3 -c "import re; print(re.search(r'__version__\s*=\s*\"([^\"]+)\"', open('${PROJECT_DIR}/agymcp/__init__.py').read()).group(1))")}"
OUT_DIR="${2:-${PROJECT_DIR}/dist}"

if ! command -v rpmbuild >/dev/null 2>&1; then
  echo "Errore: 'rpmbuild' non trovato. Installa 'rpm-build' (Fedora) o 'rpm' (Ubuntu/Debian)." >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

mkdir -p "${WORK_DIR}"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

SRC_STAGE="${WORK_DIR}/agymcp-${VERSION}"
mkdir -p "${SRC_STAGE}"
cp -r "${PROJECT_DIR}/agymcp" "${PROJECT_DIR}/assets" "${PROJECT_DIR}/README.md" "${PROJECT_DIR}/pyproject.toml" "${SRC_STAGE}/"
tar -czf "${WORK_DIR}/SOURCES/agymcp-${VERSION}.tar.gz" -C "${WORK_DIR}" "agymcp-${VERSION}"

sed "s|@VERSION@|${VERSION}|g" "${PROJECT_DIR}/packaging/fedora/agymcp.spec" > "${WORK_DIR}/SPECS/agymcp.spec"

rpmbuild \
  --define "_topdir ${WORK_DIR}" \
  --define "dist .fc" \
  -bb "${WORK_DIR}/SPECS/agymcp.spec"

RPM_FILE="$(find "${WORK_DIR}/RPMS" -name "*.rpm" -type f | head -n 1)"
if [ -z "${RPM_FILE}" ]; then
  echo "Errore: nessun file .rpm generato." >&2
  exit 1
fi

DEST_RPM="${OUT_DIR}/agymcp-${VERSION}-1.fedora.noarch.rpm"
cp "${RPM_FILE}" "${DEST_RPM}"
echo "Pacchetto Fedora RPM creato: ${DEST_RPM}"
