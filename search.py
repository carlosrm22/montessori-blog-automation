"""Google Custom Search JSON API: busca noticias Montessori en español."""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

import config
import state

logger = logging.getLogger(__name__)

CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _date_restrict() -> str:
    """Restrict results to the last 7 days."""
    return "d7"


def _search_query(query: str, retries: int = 3) -> list[dict]:
    """Execute a single CSE query with exponential backoff."""
    params = {
        "key": config.GOOGLE_CSE_KEY,
        "cx": config.GOOGLE_CSE_CX,
        "q": query,
        "lr": "lang_es",
        "gl": "mx",
        "dateRestrict": _date_restrict(),
        "num": 10,
    }
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(CSE_ENDPOINT, params=params)
                resp.raise_for_status()
                return resp.json().get("items", [])
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            wait = 2 ** (attempt + 1)
            logger.warning(
                "Search attempt %d/%d failed for '%s': %s. Retrying in %ds",
                attempt + 1, retries, query, exc, wait,
            )
            time.sleep(wait)
    logger.error("All %d search attempts failed for query: '%s'", retries, query)
    return []


def search_all() -> list[SearchResult]:
    """Run all configured queries, deduplicate, filter already processed."""
    processed_urls = state.get_all_processed_urls()
    seen_urls: set[str] = set()
    results: list[SearchResult] = []

    for query in config.SEARCH_QUERIES:
        logger.info("Buscando: '%s'", query)
        items = _search_query(query)
        for item in items:
            url = item.get("link", "")
            if not url or url in seen_urls or url in processed_urls:
                continue
            seen_urls.add(url)
            results.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=url,
                    snippet=item.get("snippet", ""),
                )
            )

    logger.info("Total resultados únicos (nuevos): %d", len(results))
    return results


if __name__ == "__main__":
    config.setup_logging()
    config.validate()
    results = search_all()
    for r in results:
        print(f"  - {r.title}\n    {r.url}\n    {r.snippet}\n")
