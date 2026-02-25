"""Evalúa relevancia de artículos con enfoque en contenido noticioso/actual."""

import json
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from google import genai

import config
from search import SearchResult

logger = logging.getLogger(__name__)

SCORING_PROMPT = """Eres un evaluador experto en educación Montessori en México.

Evalúa el siguiente artículo/noticia y devuelve un JSON con exactamente estos campos:
- relevancia: float 0-1 (relevancia para la comunidad Montessori mexicana)
- valor_educativo: float 0-1 (valor educativo del contenido)
- actualidad: float 0-1 (qué tan actual y novedoso es; penaliza contenido evergreen)
- tipo_contenido: string en {{noticia, reportaje, guia, opinion, landing, directorio, homepage, wikipedia}}
- justificacion: string breve explicando tu evaluación

Reglas clave:
- Da prioridad a contenido reciente, con hechos concretos, fechas o eventos.
- Penaliza homepages, páginas "about", FAQs, directorios y contenido enciclopédico evergreen.
- Si parece contenido institucional genérico (sin novedad), actualidad debe ser baja.

Artículo:
Título: {title}
URL: {url}
Fragmento: {snippet}

Responde SOLO con el JSON, sin markdown ni texto adicional."""

WEIGHTS = {"relevancia": 0.35, "valor_educativo": 0.25, "actualidad": 0.40}
SCORING_SCHEMA = {
    "type": "object",
    "required": [
        "relevancia", "valor_educativo", "actualidad", "tipo_contenido", "justificacion",
    ],
    "properties": {
        "relevancia": {"type": "number"},
        "valor_educativo": {"type": "number"},
        "actualidad": {"type": "number"},
        "tipo_contenido": {"type": "string"},
        "justificacion": {"type": "string"},
    },
}

NEWS_HINTS = (
    "news", "noticia", "noticias", "announcement", "press", "release",
    "congreso", "summit", "evento", "conference", "estudio", "investigación",
)
EVERGREEN_HINTS = (
    "wikipedia", "what is", "qué es", "about", "acerca", "faq", "foundation",
    "instituto", "history", "historia", "method", "método",
)
EVERGREEN_PATH_HINTS = (
    "/about", "/acerca", "/faq", "/what-is", "/montessori", "/home", "/inicio",
)


def _clamp(value: float, min_v: float = 0.0, max_v: float = 1.0) -> float:
    return max(min_v, min(max_v, value))


def _year_freshness_bonus(article: SearchResult) -> float:
    """Small bonus if snippet/title mentions current or recent year."""
    text = f"{article.title} {article.snippet}"
    years = {int(y) for y in re.findall(r"\b(20\d{2})\b", text)}
    if not years:
        return 0.0
    current = datetime.now().year
    if any(y >= current for y in years):
        return 0.10
    if any(y == current - 1 for y in years):
        return 0.05
    return -0.05


def _evergreen_penalty(article: SearchResult, tipo: str) -> float:
    """Penalty for generic/evergreen pages that are poor news candidates."""
    url = article.url.lower()
    title = article.title.lower()
    snippet = article.snippet.lower()
    domain = (urlparse(article.url).hostname or "").lower()

    penalty = 0.0
    if domain.endswith("wikipedia.org") or "wikipedia" in title:
        penalty += 0.35
    if any(h in url for h in EVERGREEN_PATH_HINTS):
        penalty += 0.15
    if urlparse(article.url).path in ("", "/"):
        penalty += 0.20
    if any(h in title or h in snippet for h in EVERGREEN_HINTS):
        penalty += 0.10
    if tipo in {"landing", "directorio", "homepage", "wikipedia"}:
        penalty += 0.20
    if any(h in title or h in snippet for h in NEWS_HINTS):
        penalty -= 0.08

    return _clamp(penalty, 0.0, 0.65)


def score_article(article: SearchResult) -> float | None:
    """Score a single article. Returns weighted score or None on failure."""
    prompt = SCORING_PROMPT.format(
        title=article.title, url=article.url, snippet=article.snippet
    )
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model=config.GEMINI_TEXT_MODEL,
            contents=prompt,
            config=genai.types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SCORING_SCHEMA,
            ),
        )
        text = (response.text or "").strip()
        try:
            data = json.loads(text)
        except Exception:
            # Defensive fallback in case model ignores strict output.
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()
            data = json.loads(text)
        weighted = sum(
            data.get(key, 0.0) * weight for key, weight in WEIGHTS.items()
        )
        tipo = str(data.get("tipo_contenido", "")).strip().lower()
        freshness_bonus = _year_freshness_bonus(article)
        evergreen_penalty = _evergreen_penalty(article, tipo)
        final_score = _clamp(weighted + freshness_bonus - evergreen_penalty)

        logger.info(
            "Score %.2f (base=%.2f, bonus=%.2f, penalty=%.2f, tipo=%s) para '%s' "
            "(rel=%.1f, edu=%.1f, act=%.1f): %s",
            final_score, weighted, freshness_bonus, evergreen_penalty, tipo or "n/a",
            article.title,
            data.get("relevancia", 0), data.get("valor_educativo", 0),
            data.get("actualidad", 0), data.get("justificacion", ""),
        )
        return final_score
    except Exception as exc:
        logger.warning("Error scoring '%s': %s", article.title, exc)
        return None


def select_best(articles: list[SearchResult]) -> tuple[SearchResult, float] | None:
    """Score all articles and return the best one above threshold."""
    best: tuple[SearchResult, float] | None = None
    for article in articles:
        score = score_article(article)
        if score is None:
            continue
        if score < config.MIN_USABILITY_SCORE:
            logger.info("Descartado (score %.2f < %.2f): %s",
                        score, config.MIN_USABILITY_SCORE, article.title)
            continue
        if best is None or score > best[1]:
            best = (article, score)

    if best:
        logger.info("Mejor artículo (score %.2f): %s", best[1], best[0].title)
    else:
        logger.warning("Ningún artículo superó el umbral de %.2f", config.MIN_USABILITY_SCORE)
    return best


if __name__ == "__main__":
    config.setup_logging()
    config.validate()
    test = SearchResult(
        title="Nueva escuela Montessori abre en CDMX",
        url="https://example.com/noticia",
        snippet="Una nueva escuela con método Montessori abrirá sus puertas en la Ciudad de México.",
    )
    score = score_article(test)
    print(f"Score: {score}")
