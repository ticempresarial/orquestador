"""
Deploy de módulos Perfex CRM — Fase 2.

Copia el módulo construido de `~/work/<slug>/` a `~/www/perfex/modules/<slug>/`
y lo activa en Perfex (registra en tbloptions::active_modules).

Para otros stacks (WP/Laravel/CI3/Node) se hará otro deployer separado.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

log = logging.getLogger("orquestador.perfex_deploy")


PERFEX_MODULES_DIR = Path("/Users/datacole/www/perfex/modules")


async def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Ejecuta cmd y devuelve (code, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except Exception as e:  # noqa: BLE001
        return -1, "", f"{type(e).__name__}: {e}"
    return proc.returncode or 0, stdout_b.decode(errors="replace"), stderr_b.decode(errors="replace")


def copy_module_to_perfex(slug: str, work_dir: Path) -> tuple[bool, str]:
    """Copia ~/work/<slug>/ a ~/www/perfex/modules/<slug>/.

    Si el destino ya existe, lo reemplaza (backup como <slug>.bak).
    """
    src = work_dir
    if not src.exists():
        return False, f"No existe origen: {src}"

    dst = PERFEX_MODULES_DIR / slug
    if dst.exists():
        backup = PERFEX_MODULES_DIR / f"{slug}.bak"
        if backup.exists():
            shutil.rmtree(backup)
        shutil.move(str(dst), str(backup))
        log.info("backup previo movido a %s", backup)

    try:
        shutil.copytree(src, dst)
    except Exception as e:  # noqa: BLE001
        return False, f"copytree falló: {e}"

    # Permisos básicos: 755 dirs, 644 files
    for root, dirs, files in os.walk(dst):
        for d in dirs:
            os.chmod(Path(root) / d, 0o755)
        for f in files:
            os.chmod(Path(root) / f, 0o644)

    # Carpetas escribibles por Perfex
    for sub in ("uploads", "cache", "logs"):
        p = dst / sub
        if p.exists():
            os.chmod(p, 0o775)

    return True, f"Copiado {src} → {dst}"


async def activate_module_in_perfex(
    slug: str,
    db_host: str = "localhost",
    db_user: str = "perfex",
    db_password: str = "PerfexDev2026!#",
    db_name: str = "perfex_dev",
) -> tuple[bool, str]:
    """Marca el módulo como activo en tbloptions.

    Perfex guarda módulos activos en `tbloptions` con `name='active_modules'`
    como JSON array. Sumamos el slug si no está.
    """
    sql = f"""
SET @current := (SELECT value FROM tbloptions WHERE name='active_modules' LIMIT 1);
SET @current := IFNULL(@current, '[]');

-- Si ya está, no hacemos nada. Si no, lo agregamos.
INSERT INTO tbloptions (name, value, autoload)
SELECT 'active_modules', JSON_ARRAY('{slug}'), 'no'
WHERE NOT EXISTS (SELECT 1 FROM tbloptions WHERE name='active_modules');

UPDATE tbloptions
SET value = JSON_ARRAY_APPEND(value, '$', '{slug}')
WHERE name='active_modules'
  AND NOT JSON_CONTAINS(value, JSON_QUOTE('{slug}'));

SELECT value FROM tbloptions WHERE name='active_modules';
"""

    cmd = [
        "mysql",
        f"-h{db_host}",
        f"-u{db_user}",
        f"-p{db_password}",
        db_name,
        "-e",
        sql,
    ]
    code, stdout, stderr = await _run(cmd, timeout=15)
    if code != 0:
        return False, f"MySQL falló: {stderr[:200]}"
    return True, f"Módulo activado. active_modules ahora: {stdout.strip()[:200]}"


def run_install_php(slug: str) -> tuple[bool, str]:
    """Si el módulo tiene install.php con función modulo_install_<slug>,
    se debe ejecutar al activarlo. Perfex lo hace en su admin/modules,
    pero podemos forzarlo via CLI.

    Esto es un placeholder — Perfex requiere bootstrap completo de CI3
    para correr el install.php. Mejor delegarlo al admin web del Perfex.
    """
    install_path = PERFEX_MODULES_DIR / slug / "install.php"
    if not install_path.exists():
        return True, "No hay install.php (módulo sin migraciones)"
    return True, (
        "install.php existe. Para ejecutarlo, ir a "
        "https://mcperfex.codmira.com/admin/modules y activar el módulo desde la UI."
    )


async def desplegar_modulo_perfex(slug: str, work_dir: Path) -> tuple[bool, str]:
    """Pipeline completo de deploy:
    1. Copia ~/work/<slug>/ a ~/www/perfex/modules/<slug>/
    2. Activa en tbloptions
    3. Reporta URL para activación manual via UI
    """
    # 1. Copiar
    ok, msg_copy = copy_module_to_perfex(slug, work_dir)
    if not ok:
        return False, f"Copy: {msg_copy}"

    # 2. Activar en BD (best effort — el admin web es la forma oficial)
    ok_db, msg_db = await activate_module_in_perfex(slug)

    # 3. install.php
    ok_inst, msg_inst = run_install_php(slug)

    return True, (
        f"✅ Deploy OK\n\n"
        f"  Copy: {msg_copy}\n"
        f"  BD: {msg_db}\n"
        f"  Install: {msg_inst}\n\n"
        f"Abrir admin para confirmar:\n"
        f"  https://mcperfex.codmira.com/admin/modules\n"
        f"  https://mcperfex.codmira.com/admin/{slug}"
    )
