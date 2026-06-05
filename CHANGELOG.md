# Changelog

Sigue [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) y [SemVer](https://semver.org/).

## [0.7.2] - 2026-06-05

### Added — Auto-detección de patrones sleep/wake

Si en idle/done el usuario manda directamente `sleep 02:00`, `wake 07:00`,
`sleep 23:30 wake 06:30`, `cancelar`, `ver`, etc., el bot lo procesa como
schedule sin necesitar tappear el botón inline ni usar `/programar`.

Regex de detección (case-insensitive, empieza con):
```
^\s*(sleep|wake|wakeup|despertar|cancelar|cancel|ver|status|list)\b
```

Si el texto no matchea → sigue al modo libre Claude como antes.

## [0.7.1] - 2026-06-05

### Fixed — Sleep programado ahora FUERZA la suspensión

**Problema previo**: `pmset schedule sleep` programa un sleep "suave" que
respeta las assertions activas del sistema (mouse en uso, SSH abierta,
display on, etc.). En test real, macOS mostraba el aviso de 60s pero al
cumplirse el plazo, **cancelaba silenciosamente** el sleep si había
cualquier actividad. Imposible de usar para "duerme a las 02:00 sí o sí".

**Fix**: ahora `schedule_sleep_at` ejecuta dos cosas en paralelo:
1. `sudo pmset schedule sleep <ts>` — para que aparezca en `pmset -g sched`
   y muestre el aviso 60s antes.
2. Background bash con marker: `nohup bash -c "sleep N && pmset sleepnow"`.
   `pmset sleepnow` IGNORA assertions y fuerza el sleep aunque haya mouse,
   SSH, display on, etc.

El background process se identifica con marker
`orquestador-force-sleep=<unix_ts>` en el comando, para poder cancelarlo
luego con `pkill -f`.

### Cambios

- `system.py`:
  - `schedule_sleep_at` ahora hace híbrido (pmset + background bash).
  - `cancel_all_schedules` también limpia procesos background.
  - `list_schedules` ahora muestra schedules pmset + sleeps forzados
    pendientes con segundos restantes.

## [0.7.0] - 2026-06-05

### Added — Programación de sleep / wake desde Telegram

- `telegram-bot/system.py`:
  - `parse_schedule_input(text)` — parsea `sleep 02:00`, `sleep 23:30 wake 07:00`,
    `wake 09:00`, `cancelar`, `ver`. Si la hora ya pasó hoy, va para mañana.
    Si wake es antes de sleep, asume wake al día siguiente.
  - `schedule_sleep_at(when)` → `sudo pmset schedule sleep "MM/dd/yy HH:mm:ss"`
  - `schedule_wake_at(when)` → `sudo pmset schedule wakeorpoweron ...`
  - `cancel_all_schedules()` → `sudo pmset schedule cancelall`
  - `list_schedules()` → `pmset -g sched` (sin sudo)
- `telegram-bot/keyboards.py` — `sistema_inline_keyboard` ahora incluye:
  - 📅 Programar sleep/wake
  - 📋 Ver programación
  - 🗑️ Cancelar todas
- `telegram-bot/bot.py`:
  - Nuevo estado `awaiting_schedule_input` por user_id
  - Handler `_flow_recibir_schedule` que parsea el texto del usuario
  - Callbacks `sys:prog:ask`, `sys:prog:list`, `sys:prog:cancel:ask|do`
  - Comando texto directo: `/programar sleep 02:00 wake 07:00`
  - `/programar` sin args → entra al modo interactivo

### Requerido adicional (sudoers)

Para que `/programar` funcione sin pedir password, agregar pmset al sudoers
config junto con shutdown:

```bash
echo "datacole ALL=(ALL) NOPASSWD: /sbin/shutdown, /usr/sbin/shutdown, /usr/bin/pmset" \
  | sudo tee /etc/sudoers.d/datacole-power \
  && sudo chmod 0440 /etc/sudoers.d/datacole-power
```

`list_schedules` y `parse_schedule_input` funcionan sin sudo.

## [0.6.0] - 2026-06-05

### Added — Power management + Health desde Telegram

- `telegram-bot/system.py`:
  - `sleep_mac()` → `pmset sleepnow` (sin sudo)
  - `restart_mac()` → `sudo -n shutdown -r now` (requiere sudoers config)
  - `health_summary()` → uptime + disco + RAM + servicios críticos
    (bot/cloudflared/nginx/mariadb) + endpoints (mcperfex, mcdev)
- `telegram-bot/keyboards.py`:
  - Nuevo botón `⚙️ Sistema` en MAIN_KEYBOARD
  - `sistema_inline_keyboard()` con 3 acciones (Health / Sleep / Restart)
  - `sistema_confirmar_keyboard()` con Sí/No para acciones destructivas
- `telegram-bot/bot.py`:
  - Handler `cmd_sistema` (alias: `/sistema`, `/health`)
  - `_handle_sys_callback` procesa `sys:health`, `sys:sleep:ask|do`, `sys:restart:ask|do`
  - Sleep y restart piden confirmación inline antes de ejecutar
  - Si restart falla por sudo, el mensaje explica cómo configurar sudoers

### Requerido (configuración manual)

Para que `/restart` funcione sin pedir password, ejecutar UNA vez en SSH:

```bash
echo "datacole ALL=(ALL) NOPASSWD: /sbin/shutdown, /usr/sbin/shutdown" \
  | sudo tee /etc/sudoers.d/datacole-power \
  && sudo chmod 0440 /etc/sudoers.d/datacole-power
```

`/sleep` y `/health` funcionan sin configuración adicional.

## [0.5.0] - 2026-06-05

### Added — intake con contexto rico por stack

**Problema resuelto**: el intake hacía preguntas obvias (auth, roles, i18n,
DB) que ya están resueltas por el stack base. El usuario quedaba abrumado
con preguntas que cualquier dev de Perfex/WP/Laravel ya da por hecho.

- `telegram-bot/stack_context.py` (nuevo, ~22 KB):
  - `PERFEX_CONTEXT`: detalle de entidades nativas (customers, leads, staff,
    invoices, etc.), infraestructura (hooks, i18n, permissions, etc.),
    patrón de módulo (`modules/<nombre>/`), preguntas BUENAS vs MALAS.
  - `WP_CONTEXT`: WordPress core + WooCommerce ecosystem.
  - `LARAVEL_CONTEXT`: Laravel 12 + Livewire + Tailwind v4 (estilo MailTrixy).
  - `CI3_CONTEXT`: CI3 standalone (NO Perfex).
  - `NODE_CONTEXT`: Next.js App Router + Supabase + shadcn.
  - `GENERIC_CONTEXT`: fallback para stacks no detectados.
- `telegram-bot/intake.py`:
  - `analizar_y_preguntar` ahora hace **2 llamadas a Claude**:
    1. Detectar stack (corta, JSON con stack_detectado + nombre + slug).
    2. Con stack detectado, generar preguntas embed-eando el contexto
       rico del stack en el prompt.
  - El segundo prompt es explícito: "NO hagas preguntas MALAS, SÍ hacé las
    BUENAS según el contexto". Reduce la cantidad de preguntas obvias.
  - Devuelve nuevo campo `razon_stack` con la justificación del LLM.
- `render_preguntas_para_telegram` muestra el `razon_stack` en italics
  debajo del stack detectado.

### Notas

- El contexto vive embed en el prompt (~3-4 KB por stack). Acepta hasta
  10K tokens de extra context sin problema para Claude.
- A futuro (Fase 2+), esto puede leer los repos team-perfex/team-wp/etc.
  directamente desde el filesystem para tener contexto aún más actualizado.

## [0.3.1] - 2026-06-05

### Fixed

- `bot.py` ahora arranca con `drop_pending_updates=True`.
  Síntoma previo: tras reload del launchd con código nuevo, el bot
  procesaba mensajes que habían quedado en queue de Telegram durante
  el reinicio. El resultado era que `/start` respondía con el formato
  de la versión anterior (porque el mensaje original había llegado
  cuando v0.1.0 estaba activo).
  Fix: descartar todos los updates pendientes al arrancar. Cada
  versión solo procesa mensajes nuevos desde su inicio.

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
