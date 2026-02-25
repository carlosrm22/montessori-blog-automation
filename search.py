"""Módulo de búsqueda de noticias (Brave Search por defecto)."""

import logging
import time
from dataclasses import dataclass

import httpx

import config
import state

logger = logging.getLogger(__name__)

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


def _date_restrict() -> str:
    """Restrict results to the last 7 days."""
    return "d7"


def _search_brave(query: str, retries: int = 3) -> list[dict]:
    """Execute a Brave Search query with exponential backoff."""
    params = {
        "q": query,
        "count": 10,
        "country": "MX",
        "search_lang": "es",
    }
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
    }
    for attempt in range(retries):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(BRAVE_ENDPOINT, params=params, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
                web = payload.get("web", {})
                return web.get("results", []) if isinstance(web, dict) else []
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            wait = 2 ** (attempt + 1)
            logger.warning(
                "Brave search attempt %d/%d failed for '%s': %s. Retrying in %ds",
                attempt + 1, retries, query, exc, wait,
            )
            time.sleep(wait)
    logger.error("All %d Brave search attempts failed for query: '%s'", retries, query)
    return []


def _search_google_cse(query: str, retries: int = 3) -> list[dict]:
    """Execute a Google CSE query with exponential backoff."""
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
                "Google CSE attempt %d/%d failed for '%s': %s. Retrying in %ds",
                attempt + 1, retries, query, exc, wait,
            )
            time.sleep(wait)
    logger.error("All %d Google CSE attempts failed for query: '%s'", retries, query)
    return []


def _search_query(query: str, retries: int = 3) -> list[dict]:
    """Execute one query using configured provider."""
    if config.SEARCH_PROVIDER == "brave":
        return _search_brave(query, retries=retries)
    if config.SEARCH_PROVIDER == "google_cse":
        return _search_google_cse(query, retries=retries)
    logger.error("Unsupported SEARCH_PROVIDER: %s", config.SEARCH_PROVIDER)
    return []


def _extract_fields(item: dict) -> tuple[str, str, str]:
    """Normalize search item fields across providers."""
    if config.SEARCH_PROVIDER == "google_cse":
        return (
            item.get("title", ""),
            item.get("link", ""),
            item.get("snippet", ""),
        )
    return (
        item.get("title", ""),
        item.get("url", ""),
        item.get("description", "") or item.get("snippet", ""),
    )


def search_all() -> list[SearchResult]:
    """Run all configured queries, deduplicate, filter already processed."""
    processed_urls = state.get_all_processed_urls()
    seen_urls: set[str] = set()
    results: list[SearchResult] = []

    for query in config.SEARCH_QUERIES:
        logger.info("Buscando (%s): '%s'", config.SEARCH_PROVIDER, query)
        items = _search_query(query)
        for item in items:
            title, url, snippet = _extract_fields(item)
            if not url or url in seen_urls or url in processed_urls:
                continue
            seen_urls.add(url)
            results.append(
                SearchResult(
                    title=title,
                    url=url,
                    snippet=snippet,
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
