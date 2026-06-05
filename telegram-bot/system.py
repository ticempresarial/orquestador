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
import re
from datetime import datetime, timedelta
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


# ─────────────────────────────────────────────────────────────────────────
# Programación de sleep / wake (pmset schedule)
# ─────────────────────────────────────────────────────────────────────────


_TIME_RE = re.compile(r"\b(\d{1,2}):?(\d{2})\b")
_HHMM_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*$")


def _parse_hhmm(text: str) -> tuple[int, int] | None:
    """'02:00' '23:30' '2:00' → (h, m). None si inválido."""
    m = _HHMM_RE.match(text)
    if not m:
        return None
    h, mn = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mn <= 59:
        return h, mn
    return None


def _at_time(h: int, m: int, prefer_future: bool = True) -> datetime:
    """Devuelve datetime hoy a HH:MM. Si ya pasó y prefer_future, suma 1 día."""
    now = datetime.now()
    when = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if prefer_future and when <= now:
        when += timedelta(days=1)
    return when


def parse_schedule_input(text: str) -> dict:
    """Parsea texto de programación de sleep/wake/shutdown/poweron.

    Acepta:
      'sleep 02:00'                          (suspende)
      'sleep 23:30 wake 07:00'               (suspende + despertar)
      'apagar 02:00'                          (apaga TOTAL)
      'apagar 02:00 prender 07:00'           (apaga + auto-prender)
      'shutdown 23:00 poweron 08:00'         (alias en inglés)
      'wake 09:00' / 'prender 07:00'          (solo prender, sin sleep)
      'cancel' / 'cancelar' / 'ver' / 'status'

    Devuelve dict con keys:
      'action': 'schedule' | 'cancel' | 'list' | 'error'
      'sleep_at':    datetime | None  (suspend)
      'wake_at':     datetime | None  (wake o poweron — pmset wakeorpoweron sirve ambos)
      'shutdown_at': datetime | None  (apagado total)
      'error':       str | None
    """
    s = text.strip().lower()
    s = s.replace("/programar", "").strip()

    if not s:
        return {
            "action": "error",
            "error": "Vacío. Usá: `sleep HH:MM`, `apagar HH:MM prender HH:MM`, etc.",
        }

    if s in ("cancel", "cancelar", "cancel all", "cancelar todas", "clear"):
        return {
            "action": "cancel",
            "sleep_at": None,
            "wake_at": None,
            "shutdown_at": None,
            "error": None,
        }

    if s in ("status", "ver", "lista", "list", "schedule"):
        return {
            "action": "list",
            "sleep_at": None,
            "wake_at": None,
            "shutdown_at": None,
            "error": None,
        }

    sleep_at = None
    wake_at = None
    shutdown_at = None

    # Match 'sleep HH:MM'
    msleep = re.search(r"sleep\s+(\d{1,2}:\d{2})", s)
    if msleep:
        hm = _parse_hhmm(msleep.group(1))
        if hm is None:
            return {"action": "error", "error": f"Hora inválida tras 'sleep': {msleep.group(1)}"}
        sleep_at = _at_time(*hm)

    # Match 'apagar HH:MM' o 'shutdown HH:MM' — apagado TOTAL
    mshutdown = re.search(r"(?:apagar|apaga|shutdown|off|poweroff)\s+(\d{1,2}:\d{2})", s)
    if mshutdown:
        hm = _parse_hhmm(mshutdown.group(1))
        if hm is None:
            return {"action": "error", "error": f"Hora inválida tras 'apagar': {mshutdown.group(1)}"}
        shutdown_at = _at_time(*hm)

    # Match 'wake HH:MM' / 'despertar HH:MM' / 'prender HH:MM' / 'poweron HH:MM'
    mwake = re.search(
        r"(?:wake|wakeup|despertar|prender|enciende|encender|poweron|power)\s+(\d{1,2}:\d{2})",
        s,
    )
    if mwake:
        hm = _parse_hhmm(mwake.group(1))
        if hm is None:
            return {"action": "error", "error": f"Hora inválida tras 'wake/prender': {mwake.group(1)}"}
        wake_at = _at_time(*hm)

    # Si solo hay un HH:MM y ninguna palabra clave, asumir sleep
    if sleep_at is None and wake_at is None and shutdown_at is None:
        only = _parse_hhmm(s)
        if only is not None:
            sleep_at = _at_time(*only)

    if sleep_at is None and wake_at is None and shutdown_at is None:
        return {
            "action": "error",
            "error": (
                "No detecté hora válida.\n\nEjemplos:\n"
                "  `sleep 02:00`            _suspende (rápido despertar)_\n"
                "  `apagar 02:00 prender 07:00`   _apagado TOTAL + auto-encendido_\n"
                "  `wake 07:00`             _solo programar encendido_"
            ),
        }

    # No tiene sentido programar sleep Y shutdown al mismo tiempo
    if sleep_at and shutdown_at:
        return {
            "action": "error",
            "error": "No podés programar `sleep` y `apagar` a la vez. Usá uno solo.",
        }

    # Si wake_at <= sleep_at/shutdown_at, asumir wake al día siguiente
    ref = sleep_at or shutdown_at
    if wake_at and ref and wake_at <= ref:
        wake_at += timedelta(days=1)

    return {
        "action": "schedule",
        "sleep_at": sleep_at,
        "wake_at": wake_at,
        "shutdown_at": shutdown_at,
        "error": None,
    }


def _pmset_timestamp(dt: datetime) -> str:
    """Formato pmset: 'MM/dd/yy HH:mm:ss'."""
    return dt.strftime("%m/%d/%y %H:%M:%S")


# Marker para identificar nuestros procesos background
_FORCE_SLEEP_MARKER = "orquestador-force-sleep"
_FORCE_SHUTDOWN_MARKER = "orquestador-force-shutdown"


async def schedule_sleep_at(when: datetime) -> tuple[bool, str]:
    """Programa sleep FORZADO a la hora indicada (ignora assertions).

    Usa SOLO background bash: `sleep N && pmset sleepnow`.

    No usamos `pmset schedule sleep` porque deja residuo después de ejecutarse
    (los schedules vencidos quedan en la lista de macOS hasta el próximo reboot
    y a veces re-disparan avisos confusos).

    `pmset sleepnow` ignora assertions del sistema (mouse, SSH, display),
    así que duerme aunque haya actividad.
    """
    now = datetime.now()
    delay = int((when - now).total_seconds())
    if delay < 5:
        return False, f"❌ La hora {when.strftime('%H:%M')} ya pasó o está muy próxima."

    timestamp = int(when.timestamp())
    cmd_str = (
        f"sleep {delay} && /usr/bin/pmset sleepnow # {_FORCE_SLEEP_MARKER}={timestamp}"
    )
    try:
        await asyncio.create_subprocess_shell(
            f"nohup bash -c {shlex_quote(cmd_str)} >/dev/null 2>&1 &",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"❌ Sleep falló: {e}"

    horas = delay // 3600
    minutos = (delay % 3600) // 60
    delta_str = f"{horas}h {minutos}m" if horas else f"{minutos} min"

    return True, (
        f"💤 Sleep *FORZADO* programado para *{when.strftime('%Y-%m-%d %H:%M')}*\n"
        f"_(en {delta_str}, ignora actividad del usuario)_"
    )


def shlex_quote(s: str) -> str:
    """Quote para bash. Equivalente a shlex.quote pero sin import circular."""
    import shlex
    return shlex.quote(s)


async def schedule_wake_at(when: datetime) -> tuple[bool, str]:
    """sudo pmset schedule wakeorpoweron 'MM/dd/yy HH:mm:ss'.

    `wakeorpoweron` despierta la Mac si está dormida O la enciende si está
    apagada. Útil para combinar con sleep O con shutdown.
    """
    ts = _pmset_timestamp(when)
    code, _, stderr = await _run(
        ["sudo", "-n", "pmset", "schedule", "wakeorpoweron", ts], timeout=10
    )
    if code != 0:
        if "password" in stderr.lower() or "sudo" in stderr.lower():
            return False, "❌ sudo pidió password. Configurá sudoers para pmset (ver README)."
        return False, stderr or f"pmset exit {code}"
    return True, f"⏰ Wake/Power-on programado para *{when.strftime('%Y-%m-%d %H:%M')}*"


# ─────────────────────────────────────────────────────────────────────────
# Shutdown total (apagado completo) + power-on programado
# ─────────────────────────────────────────────────────────────────────────


async def schedule_shutdown_at(when: datetime) -> tuple[bool, str]:
    """Apaga la Mac COMPLETAMENTE a la hora indicada.

    Diferencia con sleep:
      - Sleep = suspensión, ~5W consumo, despierta rápido
      - Shutdown = apagado total, 0W consumo, requiere boot completo al prender

    Para que la Mac vuelva sola hay que programar también `poweron` con
    schedule_poweron_at — la Mac usa el RTC interno para encenderse aunque
    esté apagada.
    """
    now = datetime.now()
    delay = int((when - now).total_seconds())
    if delay < 5:
        return False, f"❌ La hora {when.strftime('%H:%M')} ya pasó o está muy próxima."

    timestamp = int(when.timestamp())
    cmd_str = (
        f"sleep {delay} && sudo -n /sbin/shutdown -h now "
        f"# {_FORCE_SHUTDOWN_MARKER}={timestamp}"
    )
    try:
        await asyncio.create_subprocess_shell(
            f"nohup bash -c {shlex_quote(cmd_str)} >/dev/null 2>&1 &",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except Exception as e:  # noqa: BLE001
        return False, f"❌ Shutdown falló: {e}"

    horas = delay // 3600
    minutos = (delay % 3600) // 60
    delta_str = f"{horas}h {minutos}m" if horas else f"{minutos} min"

    return True, (
        f"🔌 *APAGADO TOTAL* programado para *{when.strftime('%Y-%m-%d %H:%M')}*\n"
        f"_(en {delta_str} — Mac quedará 0W, no responde a Telegram)_\n\n"
        "⚠️ Si no programaste también `prender`, la Mac queda apagada hasta que la prendas físicamente."
    )


async def schedule_poweron_at(when: datetime) -> tuple[bool, str]:
    """sudo pmset schedule poweron 'MM/dd/yy HH:mm:ss'.

    Funciona aunque la Mac esté apagada (usa RTC interno).
    """
    ts = _pmset_timestamp(when)
    code, _, stderr = await _run(
        ["sudo", "-n", "pmset", "schedule", "poweron", ts], timeout=10
    )
    if code != 0:
        if "password" in stderr.lower() or "sudo" in stderr.lower():
            return False, "❌ sudo pidió password. Configurá sudoers para pmset."
        return False, stderr or f"pmset exit {code}"
    return True, f"🔋 Power-on programado para *{when.strftime('%Y-%m-%d %H:%M')}*"


async def cancel_all_schedules() -> tuple[bool, str]:
    """Cancela:
       - schedules de pmset (sudo pmset schedule cancelall)
       - procesos background de sleep forzado
       - procesos background de shutdown forzado
    """
    # 1. pmset oficial (wake/poweron)
    code, _, stderr = await _run(
        ["sudo", "-n", "pmset", "schedule", "cancelall"], timeout=10
    )
    pmset_ok = code == 0
    if not pmset_ok and ("password" in stderr.lower() or "sudo" in stderr.lower()):
        return False, "❌ sudo pidió password. Configurá sudoers para pmset."

    # 2. Background sleeps forzados
    code_sleep, _, _ = await _run(["pkill", "-f", _FORCE_SLEEP_MARKER], timeout=5)
    killed_sleep = code_sleep == 0

    # 3. Background shutdowns forzados
    code_shutdown, _, _ = await _run(["pkill", "-f", _FORCE_SHUTDOWN_MARKER], timeout=5)
    killed_shutdown = code_shutdown == 0

    msg = "🗑️ Cancelado:"
    if pmset_ok:
        msg += "\n  ✅ schedules pmset (wake/poweron)"
    else:
        msg += f"\n  ❌ pmset: {stderr or 'error'}"
    msg += "\n  ✅ background sleeps" if killed_sleep else "\n  (sin sleeps background activos)"
    msg += "\n  ✅ background shutdowns" if killed_shutdown else "\n  (sin shutdowns background activos)"
    return pmset_ok, msg


async def list_schedules() -> str:
    """Lista schedules de pmset + background de sleep forzado."""
    parts = ["📅 *Programaciones activas*", ""]

    # 1. pmset official
    code, stdout, stderr = await _run(["pmset", "-g", "sched"], timeout=5)
    if code != 0:
        parts.append(f"❌ pmset: {stderr or 'error'}")
    else:
        lines = stdout.strip().split("\n") if stdout else []
        if not lines or len(lines) <= 1:
            parts.append("_Sin schedules pmset oficiales._")
        else:
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts.append(f"  {line}")

    # 2. Background sleeps forzados
    code_bg, stdout_bg, _ = await _run(["pgrep", "-fl", _FORCE_SLEEP_MARKER], timeout=5)
    if code_bg == 0 and stdout_bg.strip():
        parts.append("")
        parts.append("*Sleep FORZADO programado:*")
        for line in stdout_bg.strip().split("\n"):
            m = re.search(rf"{_FORCE_SLEEP_MARKER}=(\d+)", line)
            if m:
                ts = int(m.group(1))
                dt = datetime.fromtimestamp(ts)
                segundos_restantes = int((dt - datetime.now()).total_seconds())
                parts.append(
                    f"  💤 {dt.strftime('%Y-%m-%d %H:%M')} (en {segundos_restantes}s)"
                )

    # 3. Background shutdowns forzados
    code_sd, stdout_sd, _ = await _run(["pgrep", "-fl", _FORCE_SHUTDOWN_MARKER], timeout=5)
    if code_sd == 0 and stdout_sd.strip():
        parts.append("")
        parts.append("*APAGADO total programado:*")
        for line in stdout_sd.strip().split("\n"):
            m = re.search(rf"{_FORCE_SHUTDOWN_MARKER}=(\d+)", line)
            if m:
                ts = int(m.group(1))
                dt = datetime.fromtimestamp(ts)
                segundos_restantes = int((dt - datetime.now()).total_seconds())
                parts.append(
                    f"  🔌 {dt.strftime('%Y-%m-%d %H:%M')} (en {segundos_restantes}s)"
                )

    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────────────────
# Health
# ─────────────────────────────────────────────────────────────────────────


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
