"""
Power management + health del sistema operativo (macOS).

Comandos del bot:
- /sleep    suspende la Mac (sin sudo, despierta con tráfico de red)
- /restart  reinicia la Mac (requiere sudoers config para shutdown -r)
- /health   uptime + disk + RAM + servicios críticos

NO se incluye /shutdown total — si la Mac queda apagada,
no podemos prenderla desde Telegram (no hay bot escuchando).
Si Jose quiere shutdown duro, hay que configurar Wake-on-LAN aparte.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger("orquestador.system")


async def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Ejecuta cmd async y devuelve (exit_code, stdout, stderr)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        return -1, "", f"timeout {timeout}s ejecutando {cmd[0]}"
    except FileNotFoundError:
        return -1, "", f"comando no encontrado: {cmd[0]}"
    except Exception as e:  # noqa: BLE001
        return -1, "", f"{type(e).__name__}: {e}"

    stdout = stdout_b.decode("utf-8", errors="replace").strip()
    stderr = stderr_b.decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, stdout, stderr


# ─────────────────────────────────────────────────────────────────────────
# Sleep
# ─────────────────────────────────────────────────────────────────────────


async def sleep_mac() -> tuple[bool, str]:
    """pmset sleepnow - suspende inmediatamente, sin sudo.

    La Mac sigue en la red mientras está dormida, el cloudflared
    y el bot quedan suspendidos pero se despiertan automáticamente
    cuando llega tráfico.
    """
    code, _, stderr = await _run(["pmset", "sleepnow"])
    if code != 0:
        return False, stderr or f"pmset exit {code}"
    return True, "💤 Mac suspendiendo. El bot se desconecta hasta que llegue tráfico de red."


# ─────────────────────────────────────────────────────────────────────────
# Restart
# ─────────────────────────────────────────────────────────────────────────


async def restart_mac() -> tuple[bool, str]:
    """sudo -n shutdown -r now — requiere sudoers config para datacole."""
    code, _, stderr = await _run(["sudo", "-n", "shutdown", "-r", "now"], timeout=15)
    if code != 0:
        if "password" in stderr.lower() or "sudo" in stderr.lower():
            return False, (
                "❌ sudo pidió password. Necesitás configurar sudoers:\n"
                "  echo 'datacole ALL=(ALL) NOPASSWD: /sbin/shutdown' | "
                "sudo tee /etc/sudoers.d/datacole-power"
            )
        return False, stderr or f"shutdown exit {code}"
    return True, "🔄 Mac reiniciando. Volvé en 1-2 min."


# ─────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────


async def _uptime_pretty() -> str:
    """Uptime tipo: '5 days, 3 hours' o 'load average: 1.5 0.8'."""
    code, stdout, _ = await _run(["uptime"])
    if code != 0:
        return "?"
    return stdout


async def _disk_root() -> str:
    """Disco / en formato '17Gi de 228Gi (8% usado)'."""
    code, stdout, _ = await _run(["df", "-h", "/"])
    if code != 0 or not stdout:
        return "?"
    lines = stdout.split("\n")
    if len(lines) < 2:
        return "?"
    parts = lines[1].split()
    if len(parts) >= 5:
        # Filesystem Size Used Avail Capacity ...
        return f"{parts[2]} usados / {parts[1]} total · {parts[3]} libres ({parts[4]})"
    return lines[1]


async def _ram_pressure() -> str:
    """memory_pressure: System-wide memory free percentage."""
    code, stdout, _ = await _run(["memory_pressure"], timeout=5)
    if code != 0:
        return "?"
    for line in stdout.split("\n"):
        if "free percentage" in line.lower():
            return line.strip()
    return stdout.split("\n")[0] if stdout else "?"


async def _process_alive(pattern: str) -> bool:
    """Verifica si hay al menos un proceso que matchee el pattern."""
    code, stdout, _ = await _run(["pgrep", "-f", pattern])
    return code == 0 and bool(stdout.strip())


async def _http_status(url: str, timeout_s: int = 5) -> str:
    """Curl al url y devuelve HTTP status (ej. '200', '503')."""
    code, stdout, _ = await _run(
        ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout_s), url],
        timeout=timeout_s + 3,
    )
    if code != 0:
        return "down"
    return stdout or "?"


async def health_summary() -> str:
    """Resumen completo de salud del Mac."""
    uptime_str = await _uptime_pretty()
    disk_str = await _disk_root()
    ram_str = await _ram_pressure()

    bot_alive = await _process_alive("telegram-bot/bot.py")
    cloudflared_alive = await _process_alive("cloudflared")
    nginx_alive = await _process_alive("nginx")
    mariadb_alive = await _process_alive("mariadbd")

    perfex_http = await _http_status("https://mcperfex.codmira.com/admin")
    mcdev_http = await _http_status("https://mcdev.codmira.com")

    def _icon(ok: bool) -> str:
        return "✅" if ok else "❌"

    lines = [
        "🩺 *Mac Mini Health*",
        "",
        f"⏱ {uptime_str}",
        "",
        f"💾 *Disco /*",
        f"   {disk_str}",
        "",
        f"🧠 *RAM*",
        f"   {ram_str}",
        "",
        f"⚙️ *Servicios*",
        f"   {_icon(bot_alive)} bot.py (orquestador)",
        f"   {_icon(cloudflared_alive)} cloudflared (tunnel)",
        f"   {_icon(nginx_alive)} nginx",
        f"   {_icon(mariadb_alive)} mariadb",
        "",
        f"🌐 *Endpoints*",
        f"   {_icon(perfex_http == '303')} mcperfex.codmira.com → HTTP {perfex_http}",
        f"   {_icon(mcdev_http == '200')} mcdev.codmira.com → HTTP {mcdev_http}",
    ]
    return "\n".join(lines)
