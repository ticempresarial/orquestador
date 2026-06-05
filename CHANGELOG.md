# Changelog

Sigue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) y [SemVer](https://semver.org/).

## [0.2.0] - 2026-06-05

### Added — Fase 0.5: autostart con launchd

- `scripts/com.ticempresarial.orquestador.plist` — LaunchAgent macOS:
  - `RunAtLoad=true` arranca al login
  - `KeepAlive=true` se relanza si crashea
  - `ThrottleInterval=30` evita spam si falla repetido
  - `EnvironmentVariables.PATH` incluye `/opt/homebrew/bin` para que el bot encuentre `claude`
  - StandardOutPath/StandardErrorPath separados (`bot.log` y `bot.err`)
- `scripts/install-autostart.sh`:
  - Mata bot corriendo en foreground (`pkill -f bot.py`)
  - Bootout previo del servicio para idempotencia
  - Copia plist a `~/Library/LaunchAgents/`
  - `launchctl bootstrap + enable`
  - Verifica con `launchctl print`
- `scripts/uninstall-autostart.sh` para revertir si hace falta

Con esto el bot sobrevive a:
- Cierre del SSH
- Logout del usuario
- Reboot de la Mac (auto-login del usuario `datacole` ya configurado)
- Corte de luz (Mac con `pmset -a autorestart 1`)

## [0.1.0] - 2026-06-05

### Added — Fase 0: bridge mínimo

- `telegram-bot/bot.py` — bridge Telegram → `claude -p` → respuesta
- Whitelist por `user_id`
- Comandos `/start` y `/estado`
- Split de respuestas largas (chunks de 4000 chars)
- Timeout configurable (default 300s)
- Logging estructurado
- `.env.example` con todas las variables documentadas
- `.gitignore` cubre secrets, venv, IDE
- README con arquitectura + plan de fases
- `docs/fase-0-bridge.md` con instalación paso a paso
- `scripts/install-mac.sh` instalador idempotente para Mac
