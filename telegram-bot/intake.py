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

from stack_context import all_stacks, get_context_for_stack

log = logging.getLogger("orquestador.intake")


# ─────────────────────────────────────────────────────────────────────────
# Prompts canónicos
# ─────────────────────────────────────────────────────────────────────────


DETECTAR_STACK_TEMPLATE = """\
Sos el agente que detecta el stack tecnológico de un prompt de proyecto.

Stacks posibles: Perfex, CI3, Node, Laravel, WP, Otro.

Devolve SOLAMENTE un JSON entre <JSON> y </JSON>. NO escribas texto antes ni
después. NO uses markdown code fence.

<JSON>
{{
  "stack_detectado": "Perfex" | "CI3" | "Node" | "Laravel" | "WP" | "Otro",
  "razon_breve": "1 oración explicando por qué",
  "nombre_sugerido": "Nombre comercial corto del producto",
  "slug": "kebab-case-ascii"
}}
</JSON>

Prompt:
---
{prompt_original}
---
"""


ANALIZAR_PROMPT_TEMPLATE = """\
Sos el agente INTAKE del orquestador de Jose Delgado (ticempresarial).
Jose mandó un prompt para un proyecto nuevo. YA detectamos el stack:

  Stack: {stack_detectado}
  Nombre sugerido: {nombre_sugerido}
  Slug: {slug}

**CRÍTICO**: leé el contexto del stack abajo. Ese contexto te dice EXACTAMENTE
qué TRAE el stack de fábrica y qué tipo de preguntas SÍ son útiles vs cuáles
son obvias y molestan al usuario.

REGLAS NO NEGOCIABLES:
1. NO hagas preguntas marcadas como "PREGUNTAS MALAS" en el contexto.
2. SÍ hacé preguntas alineadas a "PREGUNTAS BUENAS" pero adaptadas al proyecto.
3. Mínimo 4, máximo 7 preguntas. Mejor pocas y agudas que muchas obvias.
4. Cada pregunta debe clarificar algo del MÓDULO/PRODUCTO NUEVO, no de la
   infraestructura del stack base.
5. Incluí un ejemplo concreto de respuesta cuando ayude.

============ CONTEXTO DEL STACK: {stack_detectado} ============

{stack_context}

============ FIN CONTEXTO ============

PROMPT ORIGINAL DE JOSE:
---
{prompt_original}
---

Generá las preguntas. Devolve SOLAMENTE un JSON entre <JSON> y </JSON>:

<JSON>
{{
  "preguntas": [
    {{
      "id": "P1",
      "texto": "pregunta concreta sobre el módulo NUEVO",
      "ejemplo_respuesta": "ejemplo de respuesta esperada"
    }}
  ]
}}
</JSON>
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
    """Dos llamadas:
       1) Detectar stack (corta, rápida).
       2) Con stack detectado, generar preguntas usando el contexto rico
          del stack (NO preguntas obvias, sí preguntas agudas del módulo nuevo).
    """
    # ----- Fase 1: detectar stack -----
    prompt_detect = DETECTAR_STACK_TEMPLATE.format(prompt_original=prompt_original)
    ok, output_detect = await _run_claude(prompt_detect, workdir, claude_bin, timeout)
    if not ok:
        raise RuntimeError(f"claude falló al detectar stack: {output_detect}")

    detect_json = _extract_between(output_detect, "<JSON>", "</JSON>")
    if not detect_json:
        detect_json = output_detect
    try:
        detect_data = json.loads(detect_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"JSON inválido al detectar stack: {e}\n\nOutput:\n{output_detect[:500]}"
        ) from e

    stack_detectado = detect_data.get("stack_detectado", "Otro")
    if stack_detectado not in all_stacks():
        log.warning("stack desconocido '%s' → fallback a Otro", stack_detectado)
        stack_detectado = "Otro"

    nombre_sugerido = detect_data.get("nombre_sugerido", "Producto Nuevo")
    slug = detect_data.get("slug", "producto-nuevo")

    log.info(
        "intake: detectado stack=%s nombre=%s slug=%s",
        stack_detectado, nombre_sugerido, slug,
    )

    # ----- Fase 2: generar preguntas con contexto del stack -----
    stack_context_text = get_context_for_stack(stack_detectado)
    prompt_analizar = ANALIZAR_PROMPT_TEMPLATE.format(
        prompt_original=prompt_original,
        stack_detectado=stack_detectado,
        nombre_sugerido=nombre_sugerido,
        slug=slug,
        stack_context=stack_context_text,
    )
    ok, output_analizar = await _run_claude(
        prompt_analizar, workdir, claude_bin, timeout
    )
    if not ok:
        raise RuntimeError(f"claude falló al analizar: {output_analizar}")

    analizar_json = _extract_between(output_analizar, "<JSON>", "</JSON>")
    if not analizar_json:
        analizar_json = output_analizar
    try:
        analizar_data = json.loads(analizar_json)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"JSON inválido al analizar: {e}\n\nOutput:\n{output_analizar[:500]}"
        ) from e

    preguntas = analizar_data.get("preguntas")
    if not isinstance(preguntas, list) or not preguntas:
        raise RuntimeError("Sin preguntas en respuesta de intake (fase 2)")

    return {
        "stack_detectado": stack_detectado,
        "nombre_sugerido": nombre_sugerido,
        "slug": slug,
        "preguntas": preguntas,
        "razon_stack": detect_data.get("razon_breve", ""),
    }


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
    ]
    razon = data.get("razon_stack")
    if razon:
        out.append(f"_{razon}_")
    out += [
        f"Slug propuesto: `{data['slug']}`",
        "",
        f"Tengo {len(data['preguntas'])} preguntas para clarificar el módulo NUEVO:",
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
