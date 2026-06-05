#!/usr/bin/env bash
# uninstall-autostart.sh - Desinstala el LaunchAgent del bot.

set -euo pipefail

LABEL="com.ticempresarial.orquestador"
TARGET_PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

echo "==> Removiendo servicio launchd…"
launchctl bootout "gui/$(id -u)" "${TARGET_PLIST}" 2>/dev/null && echo "    OK" || echo "    no estaba cargado"

if [ -f "${TARGET_PLIST}" ]; then
  rm "${TARGET_PLIST}"
  echo "==> Plist eliminado: ${TARGET_PLIST}"
fi

echo ""
echo "✅ Autostart desinstalado. El bot ya no arrancará al login."
echo "   El bot actual (si está corriendo) seguirá vivo hasta que lo mates."
