"""
Orquestador ticempresarial - Bridge Telegram <-> Claude Code CLI.

Fase 0: bridge libre (cualquier texto -> claude -p -> respuesta).
Fase 1: comando /nuevo dispara intake estructurado:
        - Bot pide prompt inicial
        - Claude analiza y devuelve N preguntas
        - Usuario responde todas juntas
        - Claude consolida brief.md en ~/proyectos/<slug>/

Estados (por user_id) persistidos en state/sessions.json.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from intake import (
    analizar_y_preguntar,
    consolidar_brief,
    parsear_respuestas,
    render_preguntas_para_telegram,
)
from slugify import slugify
from state import StateStore

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
PROYECTOS_DIR = Path(os.getenv("PROYECTOS_DIR", str(Path.home() / "proyectos"))).expanduser()
STATE_FILE = Path(os.getenv("STATE_FILE", str(Path(__file__).parent / "state" / "sessions.json"))).expanduser()

TELEGRAM_MSG_LIMIT = 4000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("orquestador")

store = StateStore(STATE_FILE)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _is_allowed(user_id: int) -> bool:
    return user_id in ALLOWED_IDS


def _split_message(text: str, limit: int = TELEGRAM_MSG_LIMIT) -> list[str]:
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


async def _send(update: Update, text: str, parse_mode: str | None = None) -> None:
    for chunk in _split_message(text):
        await update.message.reply_text(chunk, parse_mode=parse_mode)


async def _run_claude_libre(prompt: str) -> tuple[bool, str]:
    """Modo libre (Fase 0): pasa el prompt tal cual a claude -p."""
    if not WORKDIR.exists():
        return False, f"WORKDIR no existe: {WORKDIR}"

    cmd = [CLAUDE_BIN, "-p", prompt]
    log.info("libre: %s (cwd=%s)", shlex.join(cmd[:2]), WORKDIR)

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
        return False, f"timeout {CLAUDE_TIMEOUT_SECONDS}s"
    except FileNotFoundError:
        return False, f"binario no encontrado: {CLAUDE_BIN}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return False, stderr or stdout or f"exit {proc.returncode}"
    return True, stdout or "(sin output)"


# ─────────────────────────────────────────────────────────────────────────
# Handlers
# ─────────────────────────────────────────────────────────────────────────


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    await _send(
        update,
        "Hola Jose. Orquestador ticempresarial listo.\n\n"
        "Comandos:\n"
        "  /nuevo       iniciar proyecto (intake con preguntas → brief)\n"
        "  /cancelar    cancelar proyecto en curso\n"
        "  /proyectos   listar briefs guardados\n"
        "  /verbrief    ver último brief generado\n"
        "  /estado      salud del bot\n\n"
        "Mensaje libre = modo Fase 0 (paso directo a claude -p).",
    )


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    st = await store.get(user_id)
    msg = (
        f"Bot vivo.\n"
        f"Workdir: {WORKDIR} ({'OK' if WORKDIR.exists() else 'NO EXISTE'})\n"
        f"Proyectos: {PROYECTOS_DIR}\n"
        f"Claude bin: {CLAUDE_BIN}\n"
        f"Timeout: {CLAUDE_TIMEOUT_SECONDS}s\n"
        f"Tu estado: {st['estado']}"
    )
    if st["estado"] != "idle" and st.get("proyecto_slug"):
        msg += f"\nProyecto activo: {st['proyecto_slug']}"
    await _send(update, msg)


async def cmd_nuevo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    st = await store.get(user_id)
    if st["estado"] not in ("idle", "done"):
        await _send(
            update,
            f"⚠️ Tenés un proyecto en curso ({st['estado']}): `{st.get('proyecto_slug')}`.\n"
            "Usá /cancelar para abortarlo antes de arrancar uno nuevo.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    await store.set(
        user_id,
        estado="awaiting_prompt",
        iniciado_en=datetime.now(timezone.utc).isoformat(),
    )
    await _send(
        update,
        "📝 *Nuevo proyecto*\n\n"
        "Mandame el prompt inicial en UN mensaje:\n"
        "- Qué querés construir\n"
        "- Para quién (público target)\n"
        "- Diferenciador clave vs competencia (opcional)\n"
        "- Stack si lo sabés (opcional, lo deduzco)\n\n"
        "Una vez lo reciba, analizo y hago las preguntas que falten.\n"
        "Después consolido el brief y queda guardado.\n\n"
        "`/cancelar` para abortar.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    st = await store.get(user_id)
    if st["estado"] == "idle":
        await _send(update, "No hay proyecto en curso.")
        return
    slug = st.get("proyecto_slug") or "(sin slug)"
    await store.reset(user_id)
    await _send(update, f"❌ Proyecto `{slug}` cancelado. Volvés a idle.", parse_mode=ParseMode.MARKDOWN)


async def cmd_proyectos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    if not PROYECTOS_DIR.exists():
        await _send(update, "Todavía no hay proyectos. Empezá uno con /nuevo.")
        return
    dirs = sorted([d for d in PROYECTOS_DIR.iterdir() if d.is_dir()])
    if not dirs:
        await _send(update, "Todavía no hay proyectos. Empezá uno con /nuevo.")
        return
    lines = ["📂 *Proyectos*\n"]
    for d in dirs:
        brief = d / "brief.md"
        marker = "✅" if brief.exists() else "⏳"
        lines.append(f"{marker} `{d.name}`")
    await _send(update, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def cmd_verbrief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    args = context.args or []
    slug: str | None = None
    if args:
        slug = args[0].strip()
    else:
        st = await store.get(user_id)
        slug = st.get("proyecto_slug")
    if not slug:
        await _send(update, "No hay proyecto. Usá `/verbrief <slug>` o iniciá uno con /nuevo.")
        return
    brief_path = PROYECTOS_DIR / slug / "brief.md"
    if not brief_path.exists():
        await _send(update, f"No encuentro brief en {brief_path}.")
        return
    contenido = brief_path.read_text(encoding="utf-8")
    await _send(update, contenido)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Router según estado del usuario."""
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        log.warning("rechazado user_id=%s", user_id)
        return

    texto = (update.message.text or "").strip()
    if not texto:
        return

    st = await store.get(user_id)
    estado = st["estado"]

    if estado == "awaiting_prompt":
        await _flow_recibir_prompt(update, user_id, texto)
        return

    if estado == "awaiting_answers":
        await _flow_recibir_respuestas(update, user_id, texto, st)
        return

    # idle o done => modo libre Fase 0
    await _flow_libre(update, texto)


# ─────────────────────────────────────────────────────────────────────────
# Sub-flujos Fase 1
# ─────────────────────────────────────────────────────────────────────────


async def _flow_recibir_prompt(update: Update, user_id: int, prompt_original: str) -> None:
    await update.message.chat.send_action(ChatAction.TYPING)
    await _send(update, "⏳ Analizando tu prompt y preparando preguntas…")
    try:
        data = await analizar_y_preguntar(
            prompt_original=prompt_original,
            workdir=WORKDIR,
            claude_bin=CLAUDE_BIN,
            timeout=CLAUDE_TIMEOUT_SECONDS,
        )
    except Exception as e:  # noqa: BLE001
        await store.reset(user_id)
        await _send(update, f"❌ Falló el intake: {e}\n\nVolvés a idle.")
        return

    # Asegurar slug único: si la carpeta ya existe, sufijar
    slug = slugify(data["slug"] or data["nombre_sugerido"])
    proyecto_dir = PROYECTOS_DIR / slug
    n = 2
    while proyecto_dir.exists():
        proyecto_dir = PROYECTOS_DIR / f"{slug}-{n}"
        n += 1
    slug = proyecto_dir.name
    proyecto_dir.mkdir(parents=True, exist_ok=True)

    # Guardar prompt original como referencia auditable
    (proyecto_dir / "prompt-original.md").write_text(prompt_original, encoding="utf-8")
    (proyecto_dir / "intake.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    await store.set(
        user_id,
        estado="awaiting_answers",
        proyecto_slug=slug,
        proyecto_dir=str(proyecto_dir),
        prompt_original=prompt_original,
        stack_detectado=data["stack_detectado"],
        nombre_sugerido=data["nombre_sugerido"],
        preguntas=data["preguntas"],
    )

    msg = render_preguntas_para_telegram({**data, "slug": slug})
    await _send(update, msg, parse_mode=ParseMode.MARKDOWN)


async def _flow_recibir_respuestas(
    update: Update,
    user_id: int,
    texto: str,
    st: dict,
) -> None:
    preguntas = st["preguntas"]
    respuestas = parsear_respuestas(texto, preguntas)
    faltantes = [p["id"] for p in preguntas if p["id"] not in respuestas]
    if faltantes:
        await _send(
            update,
            f"⚠️ Me faltan respuestas a: {', '.join(faltantes)}.\n\n"
            "Reenviá TODAS las respuestas en UN solo mensaje, con formato:\n"
            "```\nP1: ...\nP2: ...\n```",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await update.message.chat.send_action(ChatAction.TYPING)
    await _send(update, "⏳ Consolidando brief…")

    proyecto_dir = Path(st["proyecto_dir"])

    # Guardar respuestas crudas
    respuestas_path = proyecto_dir / "respuestas.json"
    respuestas_path.write_text(
        json.dumps(respuestas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    try:
        brief = await consolidar_brief(
            prompt_original=st["prompt_original"],
            preguntas=preguntas,
            respuestas=respuestas,
            stack_detectado=st["stack_detectado"],
            nombre_sugerido=st["nombre_sugerido"],
            slug=st["proyecto_slug"],
            workdir=WORKDIR,
            claude_bin=CLAUDE_BIN,
            timeout=CLAUDE_TIMEOUT_SECONDS,
        )
    except Exception as e:  # noqa: BLE001
        await _send(update, f"❌ Falló consolidación: {e}\nTu estado queda en awaiting_answers para reintentar.")
        return

    brief_path = proyecto_dir / "brief.md"
    brief_path.write_text(brief, encoding="utf-8")

    await store.set(user_id, estado="done")

    resumen = (
        f"✅ *Brief listo*\n\n"
        f"Proyecto: `{st['proyecto_slug']}`\n"
        f"Stack: {st['stack_detectado']}\n"
        f"Carpeta: `{proyecto_dir}`\n\n"
        f"Mandame `/verbrief` para verlo completo.\n\n"
        f"Próximo paso (Fase 2 — no implementado aún):\n"
        f"`/arrancar {st['proyecto_slug']}` invocará architect + builder."
    )
    await _send(update, resumen, parse_mode=ParseMode.MARKDOWN)


async def _flow_libre(update: Update, prompt: str) -> None:
    await update.message.chat.send_action(ChatAction.TYPING)
    await _send(update, "⏳ Procesando con Claude…")
    ok, output = await _run_claude_libre(prompt)
    prefix = "✅" if ok else "❌"
    await _send(update, f"{prefix}\n{output}")


# ─────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────


def main() -> None:
    if not TOKEN:
        raise SystemExit("Falta TELEGRAM_BOT_TOKEN en .env")
    if not ALLOWED_IDS:
        raise SystemExit("Falta ALLOWED_TELEGRAM_USER_IDS en .env")

    PROYECTOS_DIR.mkdir(parents=True, exist_ok=True)

    log.info(
        "Bot arrancando. Workdir=%s | Proyectos=%s | Allowed=%s",
        WORKDIR, PROYECTOS_DIR, ALLOWED_IDS,
    )

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("estado", cmd_estado))
    app.add_handler(CommandHandler("nuevo", cmd_nuevo))
    app.add_handler(CommandHandler("cancelar", cmd_cancelar))
    app.add_handler(CommandHandler("proyectos", cmd_proyectos))
    app.add_handler(CommandHandler("verbrief", cmd_verbrief))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
