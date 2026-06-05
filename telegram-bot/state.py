"""
Estado de sesiones por user_id, persistido en JSON.

Cada usuario de Telegram tiene UN proyecto activo a la vez (en intake).
Si ya tiene proyecto en progreso y manda /nuevo, se le avisa.

Estados posibles:
    idle              - no hay proyecto activo
    awaiting_prompt   - usuario envió /nuevo, esperamos el prompt
    awaiting_answers  - bot ya hizo preguntas, esperamos respuestas
    done              - brief consolidado, proyecto cerrado en Fase 1

El JSON se escribe atómicamente (tmp + rename) para evitar corrupción
si el bot crashea durante la escritura.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DEFAULT_STATE: dict[str, Any] = {
    "estado": "idle",
    "proyecto_slug": None,
    "proyecto_dir": None,
    "prompt_original": None,
    "stack_detectado": None,
    "nombre_sugerido": None,
    "preguntas": [],
    "iniciado_en": None,
    "actualizado_en": None,
}


class StateStore:
    """Almacén de sesiones thread-safe con persistencia JSON."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict[str, Any]] = self._load_from_disk()

    def _load_from_disk(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            with self.path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            # Corrupto - empezar limpio. El backup queda con .bak para inspección.
            try:
                self.path.rename(self.path.with_suffix(".json.bak"))
            except OSError:
                pass
            return {}

    async def _flush(self) -> None:
        """Escribe el cache a disco atómicamente (tmp + rename)."""
        tmp = self.path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._cache, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    async def get(self, user_id: int) -> dict[str, Any]:
        async with self._lock:
            key = str(user_id)
            if key not in self._cache:
                self._cache[key] = dict(_DEFAULT_STATE)
            return dict(self._cache[key])

    async def set(self, user_id: int, **fields: Any) -> dict[str, Any]:
        """Merge fields al estado del usuario y persiste."""
        async with self._lock:
            key = str(user_id)
            if key not in self._cache:
                self._cache[key] = dict(_DEFAULT_STATE)
            self._cache[key].update(fields)
            self._cache[key]["actualizado_en"] = datetime.now(timezone.utc).isoformat()
            await self._flush()
            return dict(self._cache[key])

    async def reset(self, user_id: int) -> dict[str, Any]:
        """Vuelve a idle (cancela proyecto en curso)."""
        async with self._lock:
            key = str(user_id)
            self._cache[key] = dict(_DEFAULT_STATE)
            self._cache[key]["actualizado_en"] = datetime.now(timezone.utc).isoformat()
            await self._flush()
            return dict(self._cache[key])

    async def all_states(self) -> dict[str, dict[str, Any]]:
        async with self._lock:
            return {k: dict(v) for k, v in self._cache.items()}
