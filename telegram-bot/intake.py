"""
Intake — Fase 1 del orquestador.

Dos llamadas a Claude Code CLI:

1. analizar_y_preguntar(prompt_original)
   Devuelve JSON con stack detectado, nombre sugerido, slug y 4-8 preguntas.

2. consolidar_brief(prompt_original, preguntas, respuestas, stack, nombre)
   Devuelve un brief.md estructurado en 11 secciones (basado en MASTER-PROMPT v2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex
from pathlib import Path
from typing import Any

log = logging.getLogger("orquestador.intake")


# ─────────────────────────────────────────────────────────────────────────
# Prompts canónicos
# ─────────────────────────────────────────────────────────────────────────


ANALIZAR_PROMPT_TEMPLATE = """\
Sos el agente INTAKE del orquestador de Jose Delgado (ticempresarial).
Jose acaba de mandar el prompt inicial de un proyecto nuevo. Tu trabajo:

1. Detectar el STACK probable (entre: Perfex, CI3, Node, Laravel, WP, Otro).
2. Proponer un nombre comercial corto.
3. Proponer un slug (snake o kebab, sin espacios, ASCII).
4. Hacer entre 4 y 8 preguntas que resuelvan ambigüedades, contradicciones,
   huecos o decisiones de negocio. NO preguntes cosas que ya están claras.
   Cada pregunta debe ser concreta, accionable, con ejemplo si ayuda.

Devolve SOLAMENTE un JSON entre los marcadores <JSON> y </JSON>.
NO incluyas texto antes ni después del JSON. NO uses markdown code fence.
NO expliques nada.

Esquema:
<JSON>
{{
  "stack_detectado": "Perfex" | "CI3" | "Node" | "Laravel" | "WP" | "Otro",
  "nombre_sugerido": "string corto",
  "slug": "kebab-case-ascii",
  "preguntas": [
    {{
      "id": "P1",
      "texto": "pregunta clara",
      "ejemplo_respuesta": "ejemplo opcional"
    }}
  ]
}}
</JSON>

Prompt original de Jose:
---
{prompt_original}
---
"""


CONSOLIDAR_PROMPT_TEMPLATE = """\
Sos el agente INTAKE del orquestador de Jose Delgado (ticempresarial).
Ya tenés el prompt original + las respuestas a las preguntas que hiciste.
Generá un brief.md final que servirá como CONTRATO del proyecto para las
fases siguientes (architect + builder).

Reglas del brief:
- Markdown puro
- 11 secciones en este orden exacto
- Matriz base §3 SIEMPRE incluida tal cual (no la inventes ni la quites)
- Acceptance Criteria deben ser concretos y verificables

Devolve SOLAMENTE el brief.md entre los marcadores <BRIEF> y </BRIEF>.
NO escribas nada antes ni después.

<BRIEF>
# Brief: {nombre_sugerido}

- Slug: `{slug}`
- Stack: {stack_detectado}
- Fecha: <fecha actual>
- Estado: Brief consolidado — listo para Fase 2 (Construcción)

## 1. Pitch original (literal de Jose)

> {prompt_original}

## 2. Interpretación consolidada

(Reformulación clara del pitch usando las respuestas del intake.)

## 3. Público target

(Audiencias específicas, 2-4 bullets.)

## 4. Diferenciadores vs competencia

(3-5 bullets, lo que hace único este producto.)

## 5. Stack confirmado

(Detalle: backend, frontend, DB, auth, integraciones.)

## 6. Alcance v1.0 — qué SÍ entra

(Bullet list de features concretas.)

## 7. Fuera de alcance v1.0 — qué NO entra

(Bullet list, para evitar scope creep.)

## 8. Matriz base obligatoria §3 (MASTER-PROMPT)

Estos 8 elementos van SIEMPRE, incluso si no se mencionaron:

- ✅ **Multidioma (i18n)** — interfaz traducible, sin strings hardcoded. ES + EN mínimo.
- ✅ **Modo pantalla completa** — toggle entrar/salir fullscreen.
- ✅ **Panel de notificaciones** — icono con dropdown; click marca leído automático.
- ✅ **Panel de usuario** — icono con dropdown: ajustes, perfil, cambio de contraseña.
- ✅ **Versión visible en footer** — número de versión siempre a la vista.
- ✅ **Menú lateral colapsable** — recuerda estado expandido/colapsado.
- ✅ **Tema Dark / Light / Automático** — automático sigue preferencia del OS.
- ✅ **Responsive** — desktop + mobile, probado en viewports 1920 / 1366 / 768 / 375.

## 9. Preguntas y respuestas del intake

(Pegá todas las P1, P2, ... con sus respuestas tal como las dio Jose.)

## 10. Acceptance Criteria

(Lista numerada de criterios verificables. Cada uno debe poder marcarse
como pasa/falla por el QA automático en Fase 3.)

## 11. Próximo paso

Cuando Jose esté listo, ejecutar `/arrancar {slug}` desde el bot Telegram.
Eso invocará architect del stack {stack_detectado} y luego builder.
</BRIEF>

---

Datos para llenar el brief:

PROMPT ORIGINAL:
{prompt_original}

NOMBRE SUGERIDO: {nombre_sugerido}
SLUG: {slug}
STACK DETECTADO: {stack_detectado}

PREGUNTAS Y RESPUESTAS:
{qa_block}
"""


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _extract_between(text: str, start_tag: str, end_tag: str) -> str | None:
    """Saca el contenido entre <TAG> y </TAG>."""
    pattern = re.compile(
        re.escape(start_tag) + r"(.*?)" + re.escape(end_tag),
        re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


async def _run_claude(prompt: str, workdir: Path, claude_bin: str, timeout: int) -> tuple[bool, str]:
    cmd = [claude_bin, "-p", prompt]
    log.info("intake: claude (%d chars prompt)", len(prompt))
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workdir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        return False, f"timeout ({timeout}s)"
    except FileNotFoundError:
        return False, f"binario no encontrado: {claude_bin}"
    except Exception as e:  # noqa: BLE001
        return False, f"{type(e).__name__}: {e}"

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0:
        return False, stderr or stdout or f"exit {proc.returncode}"
    return True, stdout


# ─────────────────────────────────────────────────────────────────────────
# API pública
# ─────────────────────────────────────────────────────────────────────────


async def analizar_y_preguntar(
    prompt_original: str,
    workdir: Path,
    claude_bin: str = "claude",
    timeout: int = 300,
) -> dict[str, Any]:
    """Devuelve dict con stack_detectado, nombre_sugerido, slug, preguntas[]."""
    prompt = ANALIZAR_PROMPT_TEMPLATE.format(prompt_original=prompt_original)
    ok, output = await _run_claude(prompt, workdir, claude_bin, timeout)
    if not ok:
        raise RuntimeError(f"claude falló al analizar: {output}")

    json_str = _extract_between(output, "<JSON>", "</JSON>")
    if not json_str:
        # Fallback: a veces Claude olvida los tags. Intentar parsear todo el output.
        json_str = output

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"JSON inválido del intake: {e}\n\nOutput crudo:\n{output[:500]}"
        ) from e

    # Validaciones mínimas
    for key in ("stack_detectado", "nombre_sugerido", "slug", "preguntas"):
        if key not in data:
            raise RuntimeError(f"Falta campo '{key}' en respuesta de intake")
    if not isinstance(data["preguntas"], list) or not data["preguntas"]:
        raise RuntimeError("Sin preguntas en respuesta de intake")

    return data


async def consolidar_brief(
    prompt_original: str,
    preguntas: list[dict[str, Any]],
    respuestas: dict[str, str],
    stack_detectado: str,
    nombre_sugerido: str,
    slug: str,
    workdir: Path,
    claude_bin: str = "claude",
    timeout: int = 300,
) -> str:
    """Devuelve el contenido del brief.md como string."""
    qa_lines = []
    for p in preguntas:
        pid = p.get("id", "?")
        texto = p.get("texto", "")
        resp = respuestas.get(pid, "(sin respuesta)")
        qa_lines.append(f"### {pid} — {texto}\n\n{resp}\n")
    qa_block = "\n".join(qa_lines)

    prompt = CONSOLIDAR_PROMPT_TEMPLATE.format(
        prompt_original=prompt_original,
        nombre_sugerido=nombre_sugerido,
        slug=slug,
        stack_detectado=stack_detectado,
        qa_block=qa_block,
    )

    ok, output = await _run_claude(prompt, workdir, claude_bin, timeout)
    if not ok:
        raise RuntimeError(f"claude falló al consolidar brief: {output}")

    brief = _extract_between(output, "<BRIEF>", "</BRIEF>")
    if not brief:
        # Fallback - devolver lo que sea con el tag stripeado
        brief = output.strip()

    return brief


def parsear_respuestas(texto: str, preguntas: list[dict[str, Any]]) -> dict[str, str]:
    """Parsea un mensaje del usuario que responde múltiples preguntas.

    Acepta formatos:
        "P1: respuesta\\nP2: otra"
        "P1 respuesta\\nP2 otra"
        "1. respuesta\\n2. otra"
        "respuesta 1\\nrespuesta 2"  (en orden, si N líneas == N preguntas)
    """
    ids = [p["id"] for p in preguntas]
    respuestas: dict[str, str] = {}

    # Intento 1: regex con Pn: o Pn -
    for pid in ids:
        # Match "P1: texto" o "P1 - texto" o "P1) texto" o "P1. texto"
        pattern = re.compile(
            rf"^\s*{re.escape(pid)}\s*[:\-\)\.\s]\s*(.+?)(?=^\s*P\d+\s*[:\-\)\.\s]|\Z)",
            re.IGNORECASE | re.MULTILINE | re.DOTALL,
        )
        m = pattern.search(texto)
        if m:
            respuestas[pid] = m.group(1).strip()

    if len(respuestas) == len(preguntas):
        return respuestas

    # Intento 2: si número de líneas no vacías == número de preguntas, asignar en orden
    lineas = [ln.strip() for ln in texto.split("\n") if ln.strip()]
    if len(lineas) == len(preguntas):
        # Quitar prefijos tipo "1.", "1)", "- ", etc.
        cleaned = [re.sub(r"^[\d\-\.\)\s]+", "", ln).strip() for ln in lineas]
        for pid, resp in zip(ids, cleaned):
            if pid not in respuestas and resp:
                respuestas[pid] = resp

    return respuestas


def render_preguntas_para_telegram(data: dict[str, Any]) -> str:
    """Formatea las preguntas para mandarlas en UN mensaje de Telegram."""
    out = [
        f"📋 *Intake — {data['nombre_sugerido']}*",
        f"Stack detectado: *{data['stack_detectado']}*",
        f"Slug propuesto: `{data['slug']}`",
        "",
        f"Tengo {len(data['preguntas'])} preguntas para clarificar:",
        "",
    ]
    for p in data["preguntas"]:
        out.append(f"*{p['id']}.* {p['texto']}")
        ej = p.get("ejemplo_respuesta")
        if ej:
            out.append(f"   _ej: {ej}_")
        out.append("")
    out.append("Respondé TODAS en UN solo mensaje, formato:")
    out.append("```")
    out.append("P1: tu respuesta")
    out.append("P2: tu respuesta")
    out.append("...")
    out.append("```")
    out.append("")
    out.append("O `/cancelar` si querés abortar.")
    return "\n".join(out)
