# orquestador

Bridge entre Telegram y Claude Code CLI corriendo en Mac/VPS para que **Jose Delgado** (`ticempresarial`) pueda trabajar desde el móvil.

Repo: <https://github.com/ticempresarial/orquestador>

## Qué es

Un servicio Python que:

1. Escucha mensajes en Telegram (bot `@ticempresarial_orq_bot`)
2. Cada mensaje lo pasa a `claude -p "<mensaje>"` corriendo en la Mac
3. Devuelve la respuesta de Claude por Telegram

Whitelist por `user_id` — solo Jose puede usarlo.

## No es

- ❌ Otro repo `claude-team-*` (esos son librerías de plugins .md)
- ❌ Un sistema de tickets / CRM / soporte
- ❌ Un orquestador agentic autónomo (todavía — eso es Fase 1+)

## Arquitectura

```
Móvil de Jose
    │
    │ "audita whatsappqr"
    ▼
Telegram
    │
    ▼
Mac Mini (24/7, mcdev.codmira.com)
    │
    ▼
┌─────────────────────────────────────┐
│ orquestador/telegram-bot/bot.py     │
│   ├── valida user_id                │
│   ├── recibe prompt                 │
│   └── subprocess: claude -p "..."   │
└─────┬───────────────────────────────┘
      │
      ▼
Claude Code CLI 2.x
      │
      │ usa plugins instalados:
      ▼
~/.claude/plugins/marketplaces/
      claude-team-core
      claude-team-perfex
      claude-team-ci3
      claude-team-node
      claude-team-laravel
      claude-team-wp
      │
      ▼
   respuesta
      │
      ▲
   bot.py (split en chunks 4000 chars)
      │
      ▲
   Telegram → móvil de Jose
```

## Fases

| Fase | Qué hace | Estado |
|------|----------|--------|
| **0** | Bridge mínimo Telegram → claude -p → respuesta | ✅ v0.1.0 |
| **0.5** | Autostart con launchd macOS | ✅ v0.2.0 |
| **1** | Intake con preguntas + brief consolidado en `~/proyectos/<slug>/` | ✅ v0.3.0 |
| **2** | Deploy de productos a staging local (`/arrancar <slug>`) | Pendiente |
| **3** | Motor QA con Chrome/Playwright headless | Pendiente |
| **4** | Auto-corrección de defectos | Pendiente |
| **5** | Matriz base §3 (i18n, dark mode, etc.) — ya incluida en briefs | ✅ (en Fase 1) |
| **6** | Paralelismo dinámico según RAM | Pendiente |

## Instalación en Mac

Ver [`docs/fase-0-bridge.md`](./docs/fase-0-bridge.md).

Resumen:

```bash
cd ~/orquestador
git clone https://github.com/ticempresarial/orquestador.git
cd orquestador/telegram-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# editar .env con TOKEN y USER_ID
python bot.py
```

## Estructura

```
orquestador/
├── telegram-bot/
│   ├── bot.py              # bridge principal
│   ├── requirements.txt    # python-telegram-bot, dotenv
│   ├── .env.example        # template (.env real está gitignored)
│   └── README.md
├── scripts/
│   └── install-mac.sh      # bootstrap idempotente
├── docs/
│   ├── fase-0-bridge.md    # cómo instalar y probar Fase 0
│   └── arquitectura.md
├── CHANGELOG.md
├── LICENSE                 # MIT
└── README.md               # este archivo
```

## Cómo mejorar

Cada lección de uso = un commit. Ver workflow en
[`claude-team-core/IMPROVING.md`](https://github.com/ticempresarial/claude-team-core/blob/main/IMPROVING.md).

## Licencia

MIT — uso interno de ticempresarial.
