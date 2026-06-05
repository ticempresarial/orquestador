#!/usr/bin/env bash
# install-mac.sh - Bootstrap idempotente para Fase 0 del orquestador.
#
# Uso:
#   bash install-mac.sh
#
# Asume que estás en ~/orquestador/orquestador/ después de hacer git clone.
# Crea venv, instala deps Python, copia .env.example a .env si no existe.

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$( cd "${SCRIPT_DIR}/.." && pwd )"
BOT_DIR="${REPO_DIR}/telegram-bot"

cd "${BOT_DIR}"

echo "==> Repo: ${REPO_DIR}"
echo "==> Bot dir: ${BOT_DIR}"

# venv
if [ ! -d venv ]; then
  echo "==> Creando venv"
  python3 -m venv venv
else
  echo "==> venv ya existe"
fi

# shellcheck disable=SC1091
source venv/bin/activate

echo "==> Instalando deps Python"
pip install --upgrade pip > /dev/null
pip install -r requirements.txt

# .env
if [ ! -f .env ]; then
  echo "==> Creando .env desde .env.example"
  cp .env.example .env
  echo ""
  echo "⚠️  Edita ${BOT_DIR}/.env con:"
  echo "    - TELEGRAM_BOT_TOKEN (de @BotFather)"
  echo "    - ALLOWED_TELEGRAM_USER_IDS (de @userinfobot)"
  echo ""
else
  echo "==> .env ya existe, no se sobreescribe"
fi

# verificar claude
if ! command -v claude > /dev/null; then
  echo ""
  echo "⚠️  claude CLI no está en PATH. Instalarlo con:"
  echo "    npm install -g @anthropic-ai/claude-code"
  echo "    claude login"
else
  echo "==> claude OK: $(claude --version 2>&1 | head -1)"
fi

# CLAUDE_WORKDIR del .env (si está)
WORKDIR=""
if [ -f .env ]; then
  WORKDIR="$(grep -E '^CLAUDE_WORKDIR=' .env | cut -d= -f2- | tr -d '"' | tr -d "'")"
fi

if [ -n "${WORKDIR}" ] && [ ! -d "${WORKDIR}" ]; then
  echo ""
  echo "⚠️  CLAUDE_WORKDIR no existe: ${WORKDIR}"
  echo "    Crea la carpeta o ajusta la variable en .env"
fi

echo ""
echo "================================================================="
echo " ✅ Instalación lista."
echo "================================================================="
echo ""
echo "Próximos pasos:"
echo "  1. nano ${BOT_DIR}/.env  (poner TOKEN y USER_ID)"
echo "  2. cd ${BOT_DIR} && source venv/bin/activate && python bot.py"
echo "  3. Probar desde móvil: enviar /start a @ticempresarial_orq_bot"
echo ""
