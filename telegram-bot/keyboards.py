"""
Teclados (botones) para el bot.

Dos tipos:
- MAIN_KEYBOARD: ReplyKeyboardMarkup persistente. Reemplaza el teclado del
  móvil con 6 botones grandes. Cuando se presiona, envía el texto del botón
  como mensaje.
- proyectos_inline_keyboard: InlineKeyboardMarkup contextual. Aparece en
  un mensaje específico (ej. lista de proyectos) con un botón por proyecto.
"""

from __future__ import annotations

from typing import Sequence

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# ─────────────────────────────────────────────────────────────────────────
# Texto de los botones (usado como detección en handle_text)
# ─────────────────────────────────────────────────────────────────────────

BTN_NUEVO = "📝 Nuevo"
BTN_PROYECTOS = "📂 Proyectos"
BTN_VERBRIEF = "📄 Ver brief"
BTN_ESTADO = "🩺 Estado"
BTN_CANCELAR = "❌ Cancelar"
BTN_AYUDA = "❓ Ayuda"
BTN_SISTEMA = "⚙️ Sistema"

ALL_MENU_BUTTONS = {
    BTN_NUEVO,
    BTN_PROYECTOS,
    BTN_VERBRIEF,
    BTN_ESTADO,
    BTN_CANCELAR,
    BTN_AYUDA,
    BTN_SISTEMA,
}

# ─────────────────────────────────────────────────────────────────────────
# Teclado principal — persistente, abajo del chat
# ─────────────────────────────────────────────────────────────────────────

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(BTN_NUEVO), KeyboardButton(BTN_PROYECTOS)],
        [KeyboardButton(BTN_VERBRIEF), KeyboardButton(BTN_ESTADO)],
        [KeyboardButton(BTN_CANCELAR), KeyboardButton(BTN_SISTEMA)],
        [KeyboardButton(BTN_AYUDA)],
    ],
    resize_keyboard=True,
    is_persistent=True,
    input_field_placeholder="Tap un botón o escribí un prompt…",
)


# ─────────────────────────────────────────────────────────────────────────
# Sub-menu inline de Sistema (sleep / restart / health)
# ─────────────────────────────────────────────────────────────────────────


def sistema_inline_keyboard() -> InlineKeyboardMarkup:
    """Acciones del sistema operativo Mac."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🩺 Health (status completo)", callback_data="sys:health")],
        [
            InlineKeyboardButton("💤 Sleep", callback_data="sys:sleep:ask"),
            InlineKeyboardButton("🔄 Restart", callback_data="sys:restart:ask"),
        ],
        [InlineKeyboardButton("📅 Programar sleep/wake", callback_data="sys:prog:ask")],
        [
            InlineKeyboardButton("📋 Ver programación", callback_data="sys:prog:list"),
            InlineKeyboardButton("🗑️ Cancelar todas", callback_data="sys:prog:cancel:ask"),
        ],
    ])


def sistema_confirmar_keyboard(accion: str) -> InlineKeyboardMarkup:
    """Pide confirmación antes de sleep/restart."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sí, hacelo", callback_data=f"sys:{accion}:do"),
            InlineKeyboardButton("❌ Cancelar", callback_data="sys:cancel"),
        ]
    ])


REMOVE_KEYBOARD = ReplyKeyboardRemove()


# ─────────────────────────────────────────────────────────────────────────
# Inline keyboard de proyectos (1 botón por proyecto)
# ─────────────────────────────────────────────────────────────────────────


def proyectos_inline_keyboard(slugs: Sequence[str]) -> InlineKeyboardMarkup:
    """Un botón por proyecto. Al presionar, callback `verbrief:<slug>`."""
    rows = [
        [InlineKeyboardButton(f"📄 {slug}", callback_data=f"verbrief:{slug}")]
        for slug in slugs
    ]
    if not rows:
        rows = [[InlineKeyboardButton("(sin proyectos)", callback_data="noop")]]
    return InlineKeyboardMarkup(rows)


# ─────────────────────────────────────────────────────────────────────────
# Inline keyboard de confirmación (Sí / No)
# ─────────────────────────────────────────────────────────────────────────


def confirmar_inline_keyboard(callback_yes: str, callback_no: str = "noop") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Sí", callback_data=callback_yes),
            InlineKeyboardButton("❌ No", callback_data=callback_no),
        ]
    ])
