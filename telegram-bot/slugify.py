"""Slugify mínimo sin dependencias externas."""

from __future__ import annotations

import re
import unicodedata


def slugify(text: str, max_len: int = 50) -> str:
    """Convierte texto a slug seguro para nombre de carpeta.

    Reglas:
        - Quita acentos (NFD)
        - Pasa a lowercase
        - Reemplaza no-alfanumérico por guión
        - Colapsa guiones repetidos
        - Trunca a max_len
        - Si queda vacío, devuelve "proyecto"
    """
    if not text:
        return "proyecto"

    # NFD: descompone acentos. Luego filtra solo ASCII.
    normalized = unicodedata.normalize("NFD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")

    slug = ascii_only.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    slug = slug[:max_len].rstrip("-")

    return slug or "proyecto"
