# Changelog

Sigue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) y [SemVer](https://semver.org/).

## [0.3.0] - 2026-06-05

### Added — Fase 1: intake estructurado + brief consolidado

- `telegram-bot/state.py` — StateStore con persistencia JSON atómica
  (tmp + rename), 4 estados por user_id, lock asíncrono.
- `telegram-bot/slugify.py` — slugify mínimo sin dependencias (NFD + ASCII).
- `telegram-bot/intake.py` — 2 llamadas a Claude:
  - `analizar_y_preguntar` devuelve stack detectado + nombre + slug +
    preguntas en JSON entre tags `<JSON>`.
  - `consolidar_brief` devuelve brief.md de 11 secciones entre `<BRIEF>`.
  - `parsear_respuestas` acepta varios formatos (P1:, P1 -, P1., 1., orden).
  - `render_preguntas_para_telegram` formato Markdown listo para Telegram.
- `telegram-bot/bot.py` rediseñado:
  - Router por estado del usuario (idle/awaiting_prompt/awaiting_answers/done).
  - Comandos: `/nuevo`, `/cancelar`, `/proyectos`, `/verbrief [slug]`.
  - Coexiste con modo libre Fase 0 (mensajes sin estado → claude -p directo).
- `~/proyectos/<slug>/` con `prompt-original.md`, `intake.json`,
  `respuestas.json`, `brief.md`.
- `docs/fase-1-intake.md` con flujo completo, esquema de estados y formatos.
- `.env.example` agrega `PROYECTOS_DIR` y `STATE_FILE`.

### Notas técnicas

- El brief siempre incluye la Matriz base §3 del MASTER-PROMPT (i18n,
  fullscreen, notif, user panel, footer version, sidebar colapsable,
  dark/light/auto, responsive) aunque no se mencione en el prompt original.
- El bot pregunta TODO en una sola tanda (no ping-pong), siguiendo MASTER-PROMPT.
- Stack se deduce del prompt y se confirma implícitamente en las preguntas.
- Slug colisión: si existe carpeta, sufija `-2`, `-3`, etc.

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
