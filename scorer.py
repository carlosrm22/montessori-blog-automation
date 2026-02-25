"""Evalúa relevancia de artículos usando Gemini 2.0 Flash."""

import json
import logging

from google import genai

import config
from search import SearchResult

logger = logging.getLogger(__name__)

SCORING_PROMPT = """Eres un evaluador experto en educación Montessori en México.

Evalúa el siguiente artículo/noticia y devuelve un JSON con exactamente estos campos:
- relevancia: float 0-1 (relevancia para la comunidad Montessori mexicana)
- valor_educativo: float 0-1 (valor educativo del contenido)
- actualidad: float 0-1 (qué tan actual y novedoso es)
- justificacion: string breve explicando tu evaluación

Artículo:
Título: {title}
URL: {url}
Fragmento: {snippet}

Responde SOLO con el JSON, sin markdown ni texto adicional."""

WEIGHTS = {"relevancia": 0.4, "valor_educativo": 0.35, "actualidad": 0.25}


def score_article(article: SearchResult) -> float | None:
    """Score a single article. Returns weighted score or None on failure."""
    prompt = SCORING_PROMPT.format(
        title=article.title, url=article.url, snippet=article.snippet
    )
    try:
        client = genai.Client(api_key=config.GEMINI_API_KEY)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )
        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        data = json.loads(text)
        weighted = sum(
            data.get(key, 0.0) * weight for key, weight in WEIGHTS.items()
        )
        logger.info(
            "Score %.2f para '%s' (rel=%.1f, edu=%.1f, act=%.1f): %s",
            weighted, article.title,
            data.get("relevancia", 0), data.get("valor_educativo", 0),
            data.get("actualidad", 0), data.get("justificacion", ""),
        )
        return weighted
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
