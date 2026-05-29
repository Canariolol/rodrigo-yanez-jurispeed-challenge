#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv"
ENV_EXAMPLE="${ROOT_DIR}/.env.example"
ENV_FILE="${ROOT_DIR}/.env"

python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
pip install -e "${ROOT_DIR}[dev]"

if [[ ! -f "${ENV_FILE}" ]]; then
  cp "${ENV_EXAMPLE}" "${ENV_FILE}"
  echo "Se creo ${ENV_FILE} a partir de .env.example"
else
  echo "${ENV_FILE} ya existe; se deja sin cambios"
fi

echo
echo "Bootstrap completado."
echo "Activa el entorno con: source .venv/bin/activate"
echo "Edita .env y define GLOBAL_AI_PROVIDER junto con las credenciales correspondientes."
