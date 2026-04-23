#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$(cd "${SCRIPT_DIR}/../.." && pwd)}"
PYTHON_BIN="${PYTHON_BIN:-${PROJECT_DIR}/.venv/bin/python}"
MANAGE_PY_PATH="${MANAGE_PY_PATH:-${PROJECT_DIR}/src/manage.py}"
DJANGO_SETTINGS_MODULE_VALUE="${DJANGO_SETTINGS_MODULE_VALUE:-config.settings.prod}"
LOCK_FILE="${LOCK_FILE:-/tmp/recambios_expire_inquiry_deadlines.lock}"
LOG_FILE="${LOG_FILE:-${PROJECT_DIR}/tmp/logs/expire_inquiry_deadlines.log}"

mkdir -p "$(dirname "${LOG_FILE}")"

{
  flock -n 9 || {
    printf '[%s] Skip: previous run still active.\n' "$(date --iso-8601=seconds)"
    exit 0
  }

  printf '[%s] Start expire_inquiry_deadlines\n' "$(date --iso-8601=seconds)"
  cd "${PROJECT_DIR}"
  "${PYTHON_BIN}" "${MANAGE_PY_PATH}" expire_inquiry_deadlines \
    --settings="${DJANGO_SETTINGS_MODULE_VALUE}"
  printf '[%s] End expire_inquiry_deadlines\n' "$(date --iso-8601=seconds)"
} 9>"${LOCK_FILE}" >>"${LOG_FILE}" 2>&1
