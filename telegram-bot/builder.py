"""
Builder — Fase 2 del orquestador.

Orquesta architect + builder para construir un producto (módulo Perfex,
plugin WP, etc.) desde el brief.md consolidado de Fase 1.

Pipeline:
1. ejecutar_architect(slug) — Claude lee brief + skills del stack y genera ARQUITECTURA.md
2. (usuario aprueba la arquitectura)
3. ejecutar_builder(slug) — Claude lee ARQUITECTURA.md + skills y genera el código
4. (deploy lo hace perfex_deploy.py)

Los timeouts son largos porque architect/builder pueden tardar 5-30 min.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Awaitable, Callable

log = logging.getLogger("orquestador.builder")


# ─────────────────────────────────────────────────────────────────────────
# Resolución de paths team-* por stack
# ─────────────────────────────────────────────────────────────────────────


REPOS_BASE = Path.home() / "orquestador"


_STACK_TO_REPO = {
    "Perfex": "claude-team-perfex",
    "WP": "claude-team-wp",
    "Laravel": "claude-team-laravel",
    "CI3": "claude-team-ci3",
    "Node": "claude-team-node",
}


_STACK_TO_AGENTS = {
    "Perfex": {
        "architect": "perfex-module-architect",
        "builder": "perfex-module-builder",
        "qa": "codecanyon-qa",
    },
    "WP": {
        "architect": "wp-plugin-architect",
        "builder": "wp-plugin-builder",
        "qa": "wp-plugin-auditor",
    },
    "Laravel": {
        "architect": "laravel-product-architect",
        "builder": "laravel-product-builder",
        "qa": "codecanyon-qa",
    },
    "CI3": {
        "architect": "ci3-product-architect",
        "builder": "ci3-product-builder",
        "qa": "codecanyon-qa",
    },
    "Node": {
        "architect": "node-product-architect",
        "builder": "node-product-builder",
        "qa": "codecanyon-qa",
    },
}


def team_repo_for_stack(stack: str) -> Path:
    """Mapea stack → ~/orquestador/claude-team-{stack}/."""
    repo_name = _STACK_TO_REPO.get(stack, "claude-team-core")
    return REPOS_BASE / repo_name


def agent_name_for(stack: str, kind: str) -> str:
    """Nombre del agent file (sin .md) para un stack + kind (architect/builder/qa)."""
    agents = _STACK_TO_AGENTS.get(stack, {})
    return agents.get(kind, f"{kind}")


def _read_file_safe(path: Path, max_chars: int | None = None) -> str:
    """Lee un archivo; devuelve '' si no existe. Trunca si max_chars."""
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncado]"
    return text


def read_skills_concat(stack: str, max_chars_per_skill: int = 4000) -> str:
    """Lee todos los SKILL.md del team-{stack} concatenados."""
    repo = team_repo_for_stack(stack)
    skills_dir = repo / "skills"
    if not skills_dir.exists():
        return f"(no hay skills/ en {repo})"

    out: list[str] = []
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        text = _read_file_safe(skill_md, max_chars_per_skill)
        out.append(f"\n========== SKILL: {skill_dir.name} ==========\n{text}\n")

    if not out:
        return f"(no se encontraron SKILL.md en {skills_dir})"
    return "\n".join(out)


def read_agent_file(stack: str, kind: str, max_chars: int = 6000) -> str:
    """Lee el .md del agent (architect/builder/qa) del team-{stack}."""
    repo = team_repo_for_stack(stack)
    agent_name = agent_name_for(stack, kind)
    agent_path = repo / "agents" / f"{agent_name}.md"
    text = _read_file_safe(agent_path, max_chars)
    if not text:
        return f"(no se encontró agent {agent_name} en {repo}/agents/)"
    return text


# ─────────────────────────────────────────────────────────────────────────
# Ejecutar Claude con timeout largo (architect / builder)
# ─────────────────────────────────────────────────────────────────────────


async def _run_claude_long(
    prompt: str,
    workdir: Path,
    claude_bin: str,
    timeout: int,
    label: str = "claude",
) -> tuple[bool, str, str]:
    """Ejecuta `claude -p <prompt>` async con timeout largo.

    Devuelve (ok, stdout, stderr).
    """
    log.info("%s: arrancando (timeout=%ds, prompt=%d chars)", label, timeout, len(prompt))
    cmd = [claude_bin, "-p", prompt]
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
        return False, "", f"{label} timeout {timeout}s"
    except FileNotFoundError:
        return False, "", f"binario no encontrado: {claude_bin}"
    except Exception as e:  # noqa: BLE001
        return False, "", f"{type(e).__name__}: {e}"

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
    ok = proc.returncode == 0
    log.info("%s: terminó (ok=%s, returncode=%s, stdout=%d chars)",
             label, ok, proc.returncode, len(stdout))
    return ok, stdout, stderr


def _extract_between(text: str, start: str, end: str) -> str | None:
    pattern = re.compile(re.escape(start) + r"(.*?)" + re.escape(end), re.DOTALL)
    m = pattern.search(text)
    return m.group(1).strip() if m else None


# ─────────────────────────────────────────────────────────────────────────
# Architect — genera ARQUITECTURA.md
# ─────────────────────────────────────────────────────────────────────────


ARCHITECT_PROMPT_TEMPLATE = """\
Sos el agente {agent_role} del orquestador de Jose Delgado (ticempresarial).
Tu misión: leer el BRIEF consolidado y producir un ARQUITECTURA.md detallado
que el builder pueda implementar directamente.

============================================================
INSTRUCCIONES DEL AGENT (extracto):
============================================================
{agent_md}

============================================================
SKILLS DEL STACK {stack}:
============================================================
{skills_md}

============================================================
BRIEF CONSOLIDADO (entrada):
============================================================
{brief_md}

============================================================
SALIDA REQUERIDA:
============================================================

Devolvé SOLAMENTE el contenido del ARQUITECTURA.md entre los marcadores
<ARQUITECTURA> y </ARQUITECTURA>. NO escribas texto antes ni después.

El ARQUITECTURA.md debe incluir como mínimo (sin importar el stack):
1. Resumen ejecutivo (qué es el producto y para quién)
2. Stack confirmado y dependencias
3. Estructura de carpetas y archivos clave
4. Esquema de base de datos (tablas, columnas, índices, FK)
5. Endpoints/Routes con verbos HTTP
6. Modelos y controladores principales
7. Vistas/UI components
8. Hooks integrados con el stack base (Perfex/WP/etc.)
9. Permisos y roles
10. Strings i18n necesarios (mínimo EN + ES)
11. Migración / installer
12. Plan de testing
13. Acceptance Criteria verificables

Sé exhaustivo pero conciso. El builder leerá esto sin tener acceso al brief
original — debe ser auto-suficiente.

<ARQUITECTURA>
# ARQUITECTURA — <Nombre del producto>

...

</ARQUITECTURA>
"""


async def ejecutar_architect(
    proyecto_dir: Path,
    stack: str,
    claude_bin: str = "claude",
    timeout: int = 1800,
) -> tuple[bool, str]:
    """Lee brief.md, invoca architect, escribe ARQUITECTURA.md.

    Devuelve (ok, mensaje). Si ok=True, mensaje = path al ARQUITECTURA.md.
    Si ok=False, mensaje = error.
    """
    brief_path = proyecto_dir / "brief.md"
    brief_md = _read_file_safe(brief_path)
    if not brief_md:
        return False, f"No hay brief.md en {proyecto_dir}"

    agent_md = read_agent_file(stack, "architect")
    skills_md = read_skills_concat(stack)
    agent_role = agent_name_for(stack, "architect").upper().replace("-", "_")

    prompt = ARCHITECT_PROMPT_TEMPLATE.format(
        agent_role=agent_role,
        agent_md=agent_md,
        skills_md=skills_md,
        brief_md=brief_md,
        stack=stack,
    )

    ok, stdout, stderr = await _run_claude_long(
        prompt, proyecto_dir, claude_bin, timeout, label="architect"
    )
    if not ok:
        return False, stderr or "architect falló sin stderr"

    arq_content = _extract_between(stdout, "<ARQUITECTURA>", "</ARQUITECTURA>")
    if not arq_content:
        arq_content = stdout.strip()

    arq_path = proyecto_dir / "ARQUITECTURA.md"
    arq_path.write_text(arq_content, encoding="utf-8")
    log.info("architect OK: escribió %d chars en %s", len(arq_content), arq_path)
    return True, str(arq_path)


# ─────────────────────────────────────────────────────────────────────────
# Builder — genera el código del producto
# ─────────────────────────────────────────────────────────────────────────


BUILDER_PROMPT_TEMPLATE = """\
Sos el agente {agent_role} del orquestador de Jose Delgado (ticempresarial).
Tu misión: leer el ARQUITECTURA.md aprobado y producir TODOS los archivos
de código del producto, listos para deploy.

============================================================
INSTRUCCIONES DEL AGENT (extracto):
============================================================
{agent_md}

============================================================
SKILLS DEL STACK {stack}:
============================================================
{skills_md}

============================================================
ARQUITECTURA APROBADA (entrada):
============================================================
{arq_md}

============================================================
SALIDA REQUERIDA:
============================================================

Vas a generar TODOS los archivos del producto. Usá el formato siguiente
ESTRICTAMENTE, sin texto adicional fuera de los bloques:

<FILE path="ruta/relativa/al/archivo.ext">
contenido completo del archivo aquí
</FILE>

<FILE path="otro/archivo.php">
contenido
</FILE>

Reglas:
- Las rutas son relativas a la raíz del módulo (NO incluyas el slug en la ruta).
- Incluí TODOS los archivos: manifest, install.php, controllers, models,
  views, language (EN + ES), assets (CSS+JS), migrations, README.md.
- Cumplí TODAS las reglas del stack (escape on output, prefijo en todo,
  CSRF, etc.).
- NO incluyas explicaciones — solo bloques <FILE>.

Empezá ya:
"""


def parse_file_blocks(text: str) -> list[tuple[str, str]]:
    """Extrae bloques <FILE path="...">...</FILE> del output del builder.

    Devuelve lista de (ruta_relativa, contenido).
    """
    pattern = re.compile(
        r'<FILE\s+path="([^"]+)">\s*(.*?)\s*</FILE>',
        re.DOTALL,
    )
    return [(m.group(1), m.group(2)) for m in pattern.finditer(text)]


async def ejecutar_builder(
    proyecto_dir: Path,
    work_dir: Path,
    stack: str,
    claude_bin: str = "claude",
    timeout: int = 2700,  # 45 min
) -> tuple[bool, str, int]:
    """Lee ARQUITECTURA.md, invoca builder, escribe archivos en work_dir/slug/.

    Devuelve (ok, mensaje, n_archivos_escritos).
    """
    arq_path = proyecto_dir / "ARQUITECTURA.md"
    arq_md = _read_file_safe(arq_path)
    if not arq_md:
        return False, f"No hay ARQUITECTURA.md en {proyecto_dir}", 0

    agent_md = read_agent_file(stack, "builder")
    skills_md = read_skills_concat(stack)
    agent_role = agent_name_for(stack, "builder").upper().replace("-", "_")

    prompt = BUILDER_PROMPT_TEMPLATE.format(
        agent_role=agent_role,
        agent_md=agent_md,
        skills_md=skills_md,
        arq_md=arq_md,
        stack=stack,
    )

    ok, stdout, stderr = await _run_claude_long(
        prompt, proyecto_dir, claude_bin, timeout, label="builder"
    )
    if not ok:
        return False, stderr or "builder falló sin stderr", 0

    # Guardar output crudo para debug
    (proyecto_dir / "builder-output.txt").write_text(stdout, encoding="utf-8")

    blocks = parse_file_blocks(stdout)
    if not blocks:
        return False, "Builder no devolvió bloques <FILE>. Ver builder-output.txt", 0

    work_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for rel_path, content in blocks:
        # Sanitizar path: no permitir absolutos ni traversals
        clean = rel_path.strip().lstrip("/").replace("..", "")
        target = work_dir / clean
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written += 1
        log.info("builder wrote %s (%d chars)", target, len(content))

    return True, f"{written} archivos escritos en {work_dir}", written
