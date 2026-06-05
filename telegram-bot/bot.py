"""
Orquestador ticempresarial - Bridge Telegram <-> Claude Code CLI.

Fase 0: bot mínimo que recibe mensajes en Telegram desde el móvil de Jose,
los pasa a Claude Code CLI corriendo en la Mac/VPS, y devuelve la respuesta.

Whitelist por user_id de Telegram. Cero tickets, cero CRM, cero soporte.
Solo desarrollo.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ─────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────

load_dotenv(Path(__file__).parent / ".env")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_IDS = {
    int(x.strip())
    for x in os.getenv("ALLOWED_TELEGRAM_USER_IDS", "").split(",")
    if x.strip().isdigit()
}
WORKDIR = Path(os.getenv("CLAUDE_WORKDIR", str(Path.home() / "orquestador"))).expanduser()
CLAUDE_BIN = os.getenv("CLAUDE_BIN", "claude")
CLAUDE_TIMEOUT_SECONDS = int(os.getenv("CLAUDE_TIMEOUT_SECONDS", "300"))

TELEGRAM_MSG_LIMIT = 4000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("orquestador")


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _is_allowed(user_id: int) -> bool:
    """True solo si el user_id está en la whitelist."""
    return user_id in ALLOWED_IDS


def _split_message(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
    """Telegram corta mensajes a 4096 chars. Partir respeta bordes."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    if remaining:
        chunks.append(remaining)
    return chunks


async def _run_claude(prompt: str) -> tuple[bool, str]:
    """Ejecuta `claude -p <prompt>` en WORKDIR. Devuelve (ok, output)."""
    if not WORKDIR.exists():
        return False, f"WORKDIR no existe: {WORKDIR}"

    cmd = [CLAUDE_BIN, "-p", prompt]
    log.info("Ejecutando: %s (cwd=%s)", shlex.join(cmd), WORKDIR)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(WORKDIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=CLAUDE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        return False, f"Timeout: Claude tardó >{CLAUDE_TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return False, f"No encuentro el binario `{CLAUDE_BIN}`. ¿Instalaste claude?"
    except Exception as e:  # noqa: BLE001
        return False, f"Error ejecutando claude: {type(e).__name__}: {e}"

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        msg = stderr or stdout or f"claude exit code {proc.returncode}"
        return False, msg

    return True, stdout or "(claude no devolvió output)"


# ─────────────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────────────


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not _is_allowed(user_id):
        log.warning("Acceso rechazado: user_id=%s", user_id)
        return
    await update.message.reply_text(
        "Hola Jose. Orquestador ticempresarial listo.\n\n"
        "Mándame un prompt y lo paso a Claude Code corriendo en la Mac.\n\n"
        "Comandos:\n"
        "  /start   esta ayuda\n"
        "  /estado  verifica que el bot está vivo\n"
        f"\nWorkdir: {WORKDIR}"
    )


async def estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not _is_allowed(user_id):
        return
    ok = WORKDIR.exists()
    msg = (
        f"Bot vivo.\n"
        f"Workdir: {WORKDIR} ({'OK' if ok else 'NO EXISTE'})\n"
        f"Claude bin: {CLAUDE_BIN}\n"
        f"Timeout: {CLAUDE_TIMEOUT_SECONDS}s\n"
        f"Usuarios autorizados: {len(ALLOWED_IDS)}"
    )
    await update.message.reply_text(msg)


async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else None
    if user_id is None or not _is_allowed(user_id):
        log.warning("Acceso rechazado: user_id=%s", user_id)
        return

    prompt = update.message.text or ""
    if not prompt.strip():
        return

    log.info("Prompt recibido (%d chars) de user_id=%s", len(prompt), user_id)
    await update.message.chat.send_action(ChatAction.TYPING)
    await update.message.reply_text("⏳ Procesando con Claude…")

    ok, output = await _run_claude(prompt)

    prefix = "✅" if ok else "❌"
    for chunk in _split_message(f"{prefix}\n{output}"):
        await update.message.reply_text(chunk)


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en .env")
    if not ALLOWED_IDS:
        raise SystemExit("Falta ALLOWED_TELEGRAM_USER_IDS en .env")

    log.info("Bot arrancando. Workdir=%s | Allowed=%s", WORKDIR, ALLOWED_IDS)

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("estado", estado))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
