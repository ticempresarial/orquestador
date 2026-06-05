#!/usr/bin/env bash
# install-autostart.sh
#
# Instala el LaunchAgent del bot del orquestador en macOS.
# El bot arrancará automáticamente:
#   - al login de datacole (incluido auto-login tras corte de luz)
#   - se relanza solo si crashea (KeepAlive)
#   - throttle 30s para no spamear si falla repetido
#
# Uso (desde la Mac):
#   bash ~/orquestador/orquestador/scripts/install-autostart.sh

set -euo pipefail

LABEL="com.ticempresarial.orquestador"
REPO_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
SOURCE_PLIST="${REPO_DIR}/scripts/${LABEL}.plist"
TARGET_DIR="${HOME}/Library/LaunchAgents"
TARGET_PLIST="${TARGET_DIR}/${LABEL}.plist"

echo "==> Repo: ${REPO_DIR}"
echo "==> Source plist: ${SOURCE_PLIST}"
echo "==> Target plist: ${TARGET_PLIST}"

if [ ! -f "${SOURCE_PLIST}" ]; then
  echo "❌ No encuentro el plist en ${SOURCE_PLIST}"
  exit 1
fi

# Mata cualquier bot corriendo en foreground/nohup
echo "==> Matando bot corriente (si existe)…"
pkill -f "telegram-bot/bot.py" 2>/dev/null && echo "    proceso matado" || echo "    no había nada corriendo"
sleep 2

# Crea LaunchAgents dir
mkdir -p "${TARGET_DIR}"

# Bootout previo (idempotencia) — ignora error si no estaba cargado
echo "==> Removiendo servicio previo (si existía)…"
launchctl bootout "gui/$(id -u)" "${TARGET_PLIST}" 2>/dev/null || true

# Copia plist actualizado
cp "${SOURCE_PLIST}" "${TARGET_PLIST}"
echo "==> Plist copiado"

# Bootstrap (carga + arranca por RunAtLoad)
echo "==> Cargando servicio launchd…"
launchctl bootstrap "gui/$(id -u)" "${TARGET_PLIST}"

# Habilitar (por si estaba deshabilitado)
launchctl enable "gui/$(id -u)/${LABEL}"

# Verifica
sleep 3
echo ""
echo "==> Estado del servicio:"
launchctl print "gui/$(id -u)/${LABEL}" 2>&1 | head -20 || echo "(no aparece en print)"

echo ""
echo "================================================================="
echo " ✅ Autostart instalado."
echo "================================================================="
echo ""
echo "El bot ahora arranca automáticamente:"
echo "  - al login de datacole (incluido auto-login tras boot)"
echo "  - se relanza solo si crashea"
echo ""
echo "Logs:"
echo "  tail -f ~/orquestador/orquestador/telegram-bot/bot.log"
echo "  tail -f ~/orquestador/orquestador/telegram-bot/bot.err"
echo ""
echo "Operaciones:"
echo "  - Parar:        launchctl bootout gui/\$(id -u)/${LABEL}"
echo "  - Arrancar:     launchctl bootstrap gui/\$(id -u) ~/Library/LaunchAgents/${LABEL}.plist"
echo "  - Estado:       launchctl print gui/\$(id -u)/${LABEL}"
echo "  - Reload todo:  bash ~/orquestador/orquestador/scripts/install-autostart.sh"
echo "  - Desinstalar:  bash ~/orquestador/orquestador/scripts/uninstall-autostart.sh"
echo ""
