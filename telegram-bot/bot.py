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
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import re as _re

from intake import (
    analizar_y_preguntar,
    consolidar_brief,
    parsear_respuestas,
    render_preguntas_para_telegram,
)

# Auto-detección: si el texto matchea esto, lo tratamos como schedule
# en vez de pasarlo a Claude libre. Cubre "sleep HH:MM", "wake HH:MM",
# "cancelar", "ver", combos.
_SCHEDULE_AUTODETECT = _re.compile(
    r"^\s*(sleep|wake|wakeup|despertar|cancelar|cancel|ver|status|list)\b",
    _re.IGNORECASE,
)
from keyboards import (
    ALL_MENU_BUTTONS,
    BTN_AYUDA,
    BTN_CANCELAR,
    BTN_ESTADO,
    BTN_NUEVO,
    BTN_PROYECTOS,
    BTN_SISTEMA,
    BTN_VERBRIEF,
    MAIN_KEYBOARD,
    proyectos_inline_keyboard,
    sistema_confirmar_keyboard,
    sistema_inline_keyboard,
)
from slugify import slugify
from state import StateStore
from system import (
    cancel_all_schedules,
    health_summary,
    list_schedules,
    parse_schedule_input,
    restart_mac,
    schedule_sleep_at,
    schedule_wake_at,
    sleep_mac,
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


async def _send(
    update: Update,
    text: str,
    parse_mode: str | None = None,
    reply_markup=None,
) -> None:
    """Manda 1+ chunks. reply_markup solo en el último para no spamear teclados."""
    chunks = _split_message(text)
    last = len(chunks) - 1
    for i, chunk in enumerate(chunks):
        markup = reply_markup if i == last else None
        await update.message.reply_text(chunk, parse_mode=parse_mode, reply_markup=markup)


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
    texto = (
        "👋 *Orquestador ticempresarial*\n\n"
        "Tocá uno de los botones del teclado, o escribime libre y paso a "
        "Claude Code directo (Fase 0).\n\n"
        "*Botones del teclado:*\n"
        f"  {BTN_NUEVO} — arranca un proyecto con intake guiado\n"
        f"  {BTN_PROYECTOS} — lista briefs guardados (tappeás uno y lo abre)\n"
        f"  {BTN_VERBRIEF} — muestra el brief del proyecto activo\n"
        f"  {BTN_ESTADO} — salud del bot + tu estado\n"
        f"  {BTN_CANCELAR} — cancela proyecto en curso\n"
        f"  {BTN_AYUDA} — esta ayuda\n\n"
        "_Tip: cualquier texto libre se procesa con Claude en cuanto estés idle._"
    )
    await _send(update, texto, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD)


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
    await _send(update, msg, reply_markup=MAIN_KEYBOARD)


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
    await _send(
        update,
        f"❌ Proyecto `{slug}` cancelado. Volvés a idle.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=MAIN_KEYBOARD,
    )


async def cmd_proyectos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    if not PROYECTOS_DIR.exists():
        await _send(update, "Todavía no hay proyectos. Tocá 📝 Nuevo para empezar.")
        return
    dirs = sorted([d for d in PROYECTOS_DIR.iterdir() if d.is_dir()])
    if not dirs:
        await _send(update, "Todavía no hay proyectos. Tocá 📝 Nuevo para empezar.")
        return

    # Resumen como texto + botones inline para abrir cada brief
    slugs_con_brief = [d.name for d in dirs if (d / "brief.md").exists()]
    slugs_sin_brief = [d.name for d in dirs if not (d / "brief.md").exists()]

    header = "📂 *Proyectos*\n\n"
    if slugs_sin_brief:
        header += "⏳ _Sin brief consolidado:_\n"
        for s in slugs_sin_brief:
            header += f"  • `{s}`\n"
        header += "\n"
    if slugs_con_brief:
        header += "✅ Tocá uno para ver su brief:"

    await update.message.reply_text(
        header,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=proyectos_inline_keyboard(slugs_con_brief or [d.name for d in dirs]),
    )


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
        # Sin slug, mostramos el inline keyboard de proyectos disponibles
        await cmd_proyectos(update, context)
        return
    await _enviar_brief(update, slug)


async def _enviar_brief(update: Update, slug: str) -> None:
    brief_path = PROYECTOS_DIR / slug / "brief.md"
    if not brief_path.exists():
        await _send(update, f"No encuentro brief en {brief_path}.")
        return
    contenido = brief_path.read_text(encoding="utf-8")
    await _send(update, contenido, reply_markup=MAIN_KEYBOARD)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Router según estado del usuario. Botones del MAIN_KEYBOARD se interceptan antes."""
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        log.warning("rechazado user_id=%s", user_id)
        return

    texto = (update.message.text or "").strip()
    if not texto:
        return

    # Botones del teclado tienen prioridad sobre cualquier estado.
    # Sin esto, en awaiting_prompt el bot trataría "📝 Nuevo" como el prompt inicial.
    if texto in ALL_MENU_BUTTONS:
        await _despachar_boton(update, context, texto)
        return

    st = await store.get(user_id)
    estado = st["estado"]

    if estado == "awaiting_prompt":
        await _flow_recibir_prompt(update, user_id, texto)
        return

    if estado == "awaiting_answers":
        await _flow_recibir_respuestas(update, user_id, texto, st)
        return

    if estado == "awaiting_schedule_input":
        await _flow_recibir_schedule(update, user_id, texto)
        return

    # idle o done: auto-detect de patrones sleep/wake antes de ir a Claude libre
    if _SCHEDULE_AUTODETECT.match(texto):
        log.info("auto-detect schedule pattern en texto: %s", texto[:50])
        await _flow_recibir_schedule(update, user_id, texto)
        return

    # idle o done => modo libre Fase 0
    await _flow_libre(update, texto)


async def _flow_recibir_schedule(update: Update, user_id: int, texto: str) -> None:
    """Procesa texto cuando el usuario está en estado awaiting_schedule_input."""
    parsed = parse_schedule_input(texto)
    action = parsed.get("action")

    if action == "error":
        await _send(
            update,
            f"❌ {parsed.get('error')}\n\nEjemplos:\n"
            "  `sleep 02:00`\n"
            "  `sleep 23:30 wake 07:00`\n"
            "  `wake 09:00`\n\n"
            "O `❌ Cancelar` para abortar.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if action == "cancel":
        ok, msg = await cancel_all_schedules()
        await store.set(user_id, estado="idle")
        await _send(update, msg, reply_markup=MAIN_KEYBOARD)
        return

    if action == "list":
        msg = await list_schedules()
        await store.set(user_id, estado="idle")
        await _send(update, msg, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD)
        return

    if action == "schedule":
        sleep_at = parsed.get("sleep_at")
        wake_at = parsed.get("wake_at")
        replies: list[str] = []
        ok_overall = True
        if sleep_at:
            ok, m = await schedule_sleep_at(sleep_at)
            replies.append(m)
            ok_overall = ok_overall and ok
        if wake_at:
            ok, m = await schedule_wake_at(wake_at)
            replies.append(m)
            ok_overall = ok_overall and ok
        prefix = "✅" if ok_overall else "⚠️"
        await store.set(user_id, estado="idle")
        await _send(
            update,
            f"{prefix} Programación:\n\n" + "\n".join(replies),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=MAIN_KEYBOARD,
        )
        return


async def _despachar_boton(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    boton: str,
) -> None:
    """Mapea cada botón del MAIN_KEYBOARD al comando equivalente."""
    if boton == BTN_NUEVO:
        await cmd_nuevo(update, context)
    elif boton == BTN_PROYECTOS:
        await cmd_proyectos(update, context)
    elif boton == BTN_VERBRIEF:
        await cmd_verbrief(update, context)
    elif boton == BTN_ESTADO:
        await cmd_estado(update, context)
    elif boton == BTN_CANCELAR:
        await cmd_cancelar(update, context)
    elif boton == BTN_AYUDA:
        await cmd_start(update, context)
    elif boton == BTN_SISTEMA:
        await cmd_sistema(update, context)


async def cmd_sistema(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Submenu de acciones del sistema."""
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    await update.message.reply_text(
        "⚙️ *Sistema*\n\nElegí una acción de la Mac:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=sistema_inline_keyboard(),
    )


async def cmd_programar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Comando texto directo: /programar sleep 02:00 wake 07:00."""
    user_id = update.effective_user.id
    if not _is_allowed(user_id):
        return
    args = " ".join(context.args or []).strip()
    if not args:
        # Sin args: pasamos al modo interactivo
        await store.set(user_id, estado="awaiting_schedule_input")
        await _send(
            update,
            "📅 *Programar sleep / wake*\n\n"
            "Mandame en UN mensaje:\n"
            "  `sleep 02:00`\n"
            "  `sleep 23:30 wake 07:00`\n"
            "  `wake 09:00`\n\n"
            "Si la hora ya pasó hoy, va para mañana automáticamente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    # Con args: procesar directo
    await _flow_recibir_schedule(update, user_id, args)


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja taps en inline buttons (lista de proyectos, etc.)."""
    query = update.callback_query
    if query is None:
        return
    user_id = query.from_user.id
    if not _is_allowed(user_id):
        await query.answer("no autorizado", show_alert=False)
        return

    # answer() rápido para que Telegram pare el spinner
    await query.answer()
    data = query.data or ""

    if data == "noop":
        return

    if data.startswith("verbrief:"):
        slug = data.split(":", 1)[1].strip()
        brief_path = PROYECTOS_DIR / slug / "brief.md"
        if not brief_path.exists():
            await query.message.reply_text(f"No encuentro brief en {brief_path}.")
            return
        contenido = brief_path.read_text(encoding="utf-8")
        # Cabecera contextual + brief en chunks
        await query.message.reply_text(
            f"📄 *{slug}*", parse_mode=ParseMode.MARKDOWN
        )
        for chunk in _split_message(contenido):
            await query.message.reply_text(chunk)
        return

    if data.startswith("sys:"):
        await _handle_sys_callback(query, data)
        return

    log.warning("callback no reconocido: %s", data)


async def _handle_sys_callback(query, data: str) -> None:
    """Procesa callbacks del sub-menú de sistema."""
    parts = data.split(":")
    if len(parts) < 2:
        return
    accion = parts[1]

    if accion == "health":
        await query.message.reply_text("⏳ Generando reporte de salud…")
        try:
            resumen = await health_summary()
        except Exception as e:  # noqa: BLE001
            await query.message.reply_text(f"❌ Falló health: {e}")
            return
        await query.message.reply_text(resumen, parse_mode=ParseMode.MARKDOWN)
        return

    if accion == "cancel":
        await query.message.reply_text("Cancelado.")
        return

    # Programación de sleep/wake (sub-acciones prog:ask / list / cancel)
    if accion == "prog":
        sub = parts[2] if len(parts) >= 3 else ""
        user_id = query.from_user.id

        if sub == "ask":
            await store.set(user_id, estado="awaiting_schedule_input")
            await query.message.reply_text(
                "📅 *Programar sleep / wake*\n\n"
                "Mandame en UN mensaje:\n"
                "  `sleep 02:00`              _solo sleep_\n"
                "  `sleep 23:30 wake 07:00`   _sleep + wake_\n"
                "  `wake 09:00`               _solo wake_\n\n"
                "Si la hora ya pasó hoy, se programa para mañana.\n"
                "Si `wake` es antes de `sleep`, se asume al día siguiente.\n\n"
                "También aceptado: `cancelar`, `ver`.\n\n"
                "O escribí `❌ Cancelar` desde el teclado para abortar.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        if sub == "list":
            msg = await list_schedules()
            await query.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            return

        if sub == "cancel":
            sub2 = parts[3] if len(parts) >= 4 else ""
            if sub2 == "ask":
                # sistema_confirmar_keyboard("prog:cancel") genera "sys:prog:cancel:do"
                await query.message.reply_text(
                    "🗑️ ¿Cancelar TODAS las programaciones?",
                    reply_markup=sistema_confirmar_keyboard("prog:cancel"),
                )
                return
            if sub2 == "do":
                ok, msg = await cancel_all_schedules()
                await query.message.reply_text(msg)
                return

    # Sleep / Restart con confirmación
    if accion in ("sleep", "restart"):
        if len(parts) >= 3 and parts[2] == "ask":
            etiqueta = {"sleep": "💤 Sleep (suspender)", "restart": "🔄 Restart (reiniciar)"}[accion]
            await query.message.reply_text(
                f"¿Confirmás *{etiqueta}*?\n\n"
                "_Tras la acción el bot se desconecta temporalmente "
                "y se reconecta cuando la Mac vuelva a estar disponible._",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=sistema_confirmar_keyboard(accion),
            )
            return
        if len(parts) >= 3 and parts[2] == "do":
            if accion == "sleep":
                ok, msg = await sleep_mac()
            else:
                ok, msg = await restart_mac()
            await query.message.reply_text(msg)
            return

    log.warning("sys callback desconocido: %s", data)


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
        f"Tocá 📄 *Ver brief* abajo, o tappeás el proyecto desde 📂 *Proyectos*.\n\n"
        f"Próximo paso (Fase 2 — no implementado aún):\n"
        f"`/arrancar {st['proyecto_slug']}` invocará architect + builder."
    )
    await _send(update, resumen, parse_mode=ParseMode.MARKDOWN, reply_markup=MAIN_KEYBOARD)


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
    app.add_handler(CommandHandler("sistema", cmd_sistema))
    app.add_handler(CommandHandler("health", cmd_sistema))  # alias rápido
    app.add_handler(CommandHandler("programar", cmd_programar))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))

    # drop_pending_updates=True descarta mensajes pendientes que llegaron mientras
    # el bot estaba caído o durante reinicios del launchd. Evita responder con
    # código viejo a mensajes que estaban en queue de Telegram.
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
    )


if __name__ == "__main__":
    main()
