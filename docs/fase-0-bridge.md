# Fase 0 — Bridge Telegram ↔ Claude Code

Instalación + prueba del bridge mínimo en la Mac.

## Pre-requisitos

En la Mac (`mcdev.codmira.com` / `192.168.18.100`):

- macOS 15+
- Node 20+
- `claude` CLI instalado (`npm install -g @anthropic-ai/claude-code`)
- Python 3.9+
- Sesión Claude Code logueada con cuenta Max (`claude login`)
- Bot Telegram creado con `@BotFather`, TOKEN guardado
- Tu `user_id` de Telegram (obtenerlo en `@userinfobot`)

## Instalación

### Opción A — Script automático

```bash
ssh datacole@192.168.18.100
mkdir -p ~/orquestador && cd ~/orquestador
git clone https://github.com/ticempresarial/orquestador.git
bash orquestador/scripts/install-mac.sh
```

El script:
1. Crea venv en `orquestador/telegram-bot/venv`
2. Instala `python-telegram-bot` y `python-dotenv`
3. Copia `.env.example` a `.env` si no existe
4. Te recuerda editar `.env` con TOKEN y USER_ID

### Opción B — Manual

```bash
ssh datacole@192.168.18.100
mkdir -p ~/orquestador && cd ~/orquestador
git clone https://github.com/ticempresarial/orquestador.git
cd orquestador/telegram-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # poner TOKEN y USER_ID
```

## Configuración del `.env`

```ini
TELEGRAM_BOT_TOKEN=8851739619:AAH....
ALLOWED_TELEGRAM_USER_IDS=123456789
CLAUDE_WORKDIR=/Users/datacole/orquestador
CLAUDE_BIN=claude
CLAUDE_TIMEOUT_SECONDS=300
```

- `TELEGRAM_BOT_TOKEN` — de `@BotFather`
- `ALLOWED_TELEGRAM_USER_IDS` — tu user_id de `@userinfobot` (números, separados por coma si son varios)
- `CLAUDE_WORKDIR` — directorio donde Claude trabajará. Debe contener clones de los repos `claude-team-*`
- `CLAUDE_BIN` — path al binario `claude` (default: `claude` en PATH)
- `CLAUDE_TIMEOUT_SECONDS` — timeout máximo de una invocación (default 300s)

## Lanzar bot en foreground (para probar)

```bash
cd ~/orquestador/orquestador/telegram-bot
source venv/bin/activate
python bot.py
```

Debe imprimir:

```
2026-06-05 12:34:56 [INFO] orquestador: Bot arrancando. Workdir=/Users/datacole/orquestador | Allowed={123456789}
```

## Probar desde móvil

1. Abre Telegram → busca `@ticempresarial_orq_bot`
2. `/start` → debe responder "Hola Jose. Orquestador ticempresarial listo."
3. `/estado` → debe responder con info de salud
4. Envía cualquier texto, ej. "¿qué hora es en la Mac?"
5. Bot responde con `⏳ Procesando con Claude…` y luego la respuesta

Si Claude no responde, revisar:

- ¿`claude --version` corre OK en la Mac?
- ¿Hiciste `claude login` con tu cuenta Max?
- ¿El `CLAUDE_WORKDIR` existe?
- Logs del bot en la terminal donde corre `python bot.py`

## Parar bot

`Ctrl+C` en la terminal donde corre.

## Próximo paso — autostart con launchd

Una vez funcional, configurar autostart para que el bot arranque solo
si la Mac se reinicia:

```bash
bash ~/orquestador/orquestador/scripts/install-autostart.sh
```

(Pendiente de crear — Fase 0.5)

## Troubleshooting

| Síntoma | Probable causa | Fix |
|---------|---------------|-----|
| `Falta TELEGRAM_BOT_TOKEN en .env` | `.env` vacío o no encontrado | `cp .env.example .env && nano .env` |
| Bot arranca pero no responde a mensajes | user_id no está en whitelist | Revisar `ALLOWED_TELEGRAM_USER_IDS` |
| `No encuentro el binario claude` | Path mal o claude sin instalar | `which claude` y ajustar `CLAUDE_BIN` |
| `Timeout: Claude tardó >300s` | Prompt muy pesado | Subir `CLAUDE_TIMEOUT_SECONDS` o partir prompt |
| `WORKDIR no existe` | Path mal en `.env` | Ajustar `CLAUDE_WORKDIR` |
| `(claude no devolvió output)` | Bug de claude o exit silencioso | Probar `claude -p "Hola"` a mano en SSH |
