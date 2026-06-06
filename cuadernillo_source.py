"""Fuente de generación a partir de los cuadernillos del Diplomado AMMAC.

Reemplaza la búsqueda de noticias: en vez de un SearchResult de Brave, arma uno
"sintético" por cada cuadernillo (PDF de sesión) usando el tema del slug del
archivo y, como base factual, el texto de la sesión correspondiente en el .md
fuente de la materia. No publica nada; solo provee los items a run_cuadernillos.py.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import config
import state

logger = logging.getLogger(__name__)

MAP_FILE = config.BASE_DIR / "cuadernillos_map.yml"
MAX_SOURCE_CHARS = 6000

# Anclas de "sesión" en los .md (los AMMAC no son uniformes):
#   "## Sesión 3: Título"  /  "# Sesión 3 en Classroom"  /  "### S3: Título"
_RE_SESION = re.compile(r"^#{1,4}\s*Sesi[oó]n\s+(\d+)\b(.*)$", re.IGNORECASE)
_RE_S_COMPACT = re.compile(r"^#{2,4}\s*S(\d+)\s*[:\.\-–—]\s*(.*)$")

# Líneas de metadatos del curso que NO deben alimentar el texto (evita que el
# artículo mencione el cuadernillo, Classroom, tareas, etc.).
_META_LINE = re.compile(
    r"cuadernillo|classroom|archivo a adjuntar|adjuntar|cuestionario|"
    r"actividad(es)? a entregar|tarea|quiz|rúbrica|rubrica|entrega",
    re.IGNORECASE,
)

_PDF_SESSION = re.compile(r"_s(\d+)_(.+)$", re.IGNORECASE)


@dataclass
class Cuadernillo:
    materia_id: str
    materia_name: str
    session_n: int
    slug: str            # topic slug del nombre del PDF
    topic_label: str     # slug humanizado (semilla del tema)
    source_text: str     # base factual (sesión del .md, limpia) o ""
    author_name: str
    tone_file: str
    brand_kit: str
    categories: list[str] = field(default_factory=list)
    pdf_path: str = ""

    @property
    def pseudo_url(self) -> str:
        return f"cuadernillo://{self.materia_id}/{self.slug}"

    @property
    def topic_id(self) -> str:
        return f"cuad_{self.materia_id}"


def _humanize(slug: str) -> str:
    text = slug.replace("_", " ").replace("-", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:1].upper() + text[1:] if text else text


def _strip_accents_lower(text: str) -> str:
    norm = unicodedata.normalize("NFKD", text)
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


def _parse_md_sessions(paths: list[Path]) -> dict[int, str]:
    """Devuelve {numero_sesion: cuerpo_de_texto} a partir de uno o más .md."""
    sessions: dict[int, str] = {}
    for path in paths:
        if not path.is_file():
            logger.warning("MD fuente no encontrado: %s", path)
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        anchors: list[tuple[int, int]] = []  # (line_index, session_number)
        for i, line in enumerate(lines):
            m = _RE_SESION.match(line) or _RE_S_COMPACT.match(line)
            if m:
                anchors.append((i, int(m.group(1))))
        for idx, (start, n) in enumerate(anchors):
            end = anchors[idx + 1][0] if idx + 1 < len(anchors) else len(lines)
            body = "\n".join(lines[start + 1 : end])
            sessions[n] = _clean_source_text(body)
    return sessions


def _clean_source_text(body: str) -> str:
    """Quita encabezados markdown y líneas de metadatos administrativos del curso."""
    out: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line:
            continue
        if _META_LINE.search(line):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)        # encabezados -> texto
        line = re.sub(r"^[-*]\s+", "", line)           # viñetas
        line = line.strip()
        if line:
            out.append(line)
    text = "\n".join(out).strip()
    return text[:MAX_SOURCE_CHARS]


def load_map() -> dict:
    return yaml.safe_load(MAP_FILE.read_text(encoding="utf-8")) or {}


def all_cuadernillos() -> list[Cuadernillo]:
    """Construye la lista completa de cuadernillos del corpus (sin filtrar estado)."""
    cfg = load_map()
    base = Path(cfg.get("base_dir", ""))
    items: list[Cuadernillo] = []
    for materia in cfg.get("materias", []):
        folder = base / materia["folder"]
        if not folder.is_dir():
            logger.warning("Carpeta de materia no encontrada: %s", folder)
            continue
        md_paths = [folder / name for name in materia.get("md_files", [])]
        sessions = _parse_md_sessions(md_paths) if md_paths else {}

        pdfs = sorted(p for p in folder.glob("*.pdf") if _PDF_SESSION.search(p.stem))
        seen_keys: set[str] = set()
        for pdf in pdfs:
            m = _PDF_SESSION.search(pdf.stem)
            if not m:
                continue
            n = int(m.group(1))
            slug = m.group(2).strip("_").lower()
            key = f"{n}:{slug}"
            if key in seen_keys:  # evita duplicados (ej. archivos repetidos)
                continue
            seen_keys.add(key)
            items.append(
                Cuadernillo(
                    materia_id=materia["id"],
                    materia_name=materia["folder"],
                    session_n=n,
                    slug=slug,
                    topic_label=_humanize(slug),
                    source_text=sessions.get(n, ""),
                    author_name=materia["author_name"],
                    tone_file=materia["tone_file"],
                    brand_kit=materia["brand_kit"],
                    categories=list(materia.get("categories", [])),
                    pdf_path=str(pdf),
                )
            )
    return items


def iter_cuadernillos(only_pending: bool = True) -> list[Cuadernillo]:
    """Lista de cuadernillos; por defecto solo los que faltan (según state)."""
    items = all_cuadernillos()
    if not only_pending:
        return items
    pending: list[Cuadernillo] = []
    for it in items:
        done = state.get_all_processed_urls(topic_id=it.topic_id)
        if it.pseudo_url not in done:
            pending.append(it)
    return pending


def coverage_report() -> dict:
    """Resumen para verificación: totales, con/sin fuente, por autor y por materia."""
    items = all_cuadernillos()
    by_author: dict[str, int] = {}
    by_materia: dict[str, dict] = {}
    no_source = 0
    for it in items:
        by_author[it.author_name] = by_author.get(it.author_name, 0) + 1
        mm = by_materia.setdefault(it.materia_id, {"total": 0, "con_fuente": 0})
        mm["total"] += 1
        if it.source_text:
            mm["con_fuente"] += 1
        else:
            no_source += 1
    return {
        "total": len(items),
        "sin_fuente": no_source,
        "por_autor": by_author,
        "por_materia": by_materia,
    }
