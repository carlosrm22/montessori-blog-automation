"""Fetch and extract article body metadata from source URLs."""

import json
import logging
import re

import httpx
from bs4 import BeautifulSoup

import config
from search import SearchResult

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (compatible; MontessoriBlogAutomation/1.0; +https://montessorimexico.org)"
)


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    return text


def _extract_text(soup: BeautifulSoup, max_chars: int) -> str:
    # Prefer semantic article/main before body fallback.
    node = soup.find("article") or soup.find("main") or soup.body
    if not node:
        return ""
    for bad in node.find_all(["script", "style", "noscript", "svg", "nav", "footer"]):
        bad.decompose()
    text = _clean_text(node.get_text(separator=" "))
    return text[:max_chars]


def _extract_meta(soup: BeautifulSoup) -> tuple[str, str]:
    published_at = ""
    author = ""

    meta_date_keys = [
        ("property", "article:published_time"),
        ("property", "og:published_time"),
        ("name", "pubdate"),
        ("name", "publishdate"),
        ("name", "date"),
        ("name", "dc.date"),
    ]
    for attr, key in meta_date_keys:
        tag = soup.find("meta", attrs={attr: key})
        if tag and tag.get("content"):
            published_at = _clean_text(tag["content"])
            break

    for attr, key in [("name", "author"), ("property", "article:author")]:
        tag = soup.find("meta", attrs={attr: key})
        if tag and tag.get("content"):
            author = _clean_text(tag["content"])
            break

    # JSON-LD fallback.
    if not published_at or not author:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text() or ""
            if not raw.strip():
                continue
            try:
                data = json.loads(raw)
            except Exception:
                continue
            objects = data if isinstance(data, list) else [data]
            for obj in objects:
                if not isinstance(obj, dict):
                    continue
                if not published_at and obj.get("datePublished"):
                    published_at = _clean_text(str(obj.get("datePublished")))
                if not author and obj.get("author"):
                    auth = obj["author"]
                    if isinstance(auth, dict):
                        author = _clean_text(str(auth.get("name", "")))
                    elif isinstance(auth, list) and auth and isinstance(auth[0], dict):
                        author = _clean_text(str(auth[0].get("name", "")))
                    else:
                        author = _clean_text(str(auth))
                if published_at and author:
                    break
            if published_at and author:
                break

    return published_at[:80], author[:120]


def enrich_article(article: SearchResult) -> SearchResult:
    """Fetch source article and return enriched SearchResult."""
    if not config.SOURCE_FETCH_ENABLED:
        return article
    try:
        with httpx.Client(
            timeout=25,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(article.url)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Could not fetch source '%s': %s", article.url, exc)
        return article

    ctype = (resp.headers.get("content-type") or "").lower()
    if "html" not in ctype:
        return article

    try:
        soup = BeautifulSoup(resp.text, "html.parser")
        source_text = _extract_text(soup, config.SOURCE_FETCH_MAX_CHARS)
        published_at, author = _extract_meta(soup)
        if not source_text:
            return article
        logger.info(
            "Source extracted (%d chars) for %s",
            len(source_text), article.url,
        )
        return SearchResult(
            title=article.title,
            url=article.url,
            snippet=article.snippet,
            source_text=source_text,
            source_published_at=published_at,
            source_author=author,
        )
    except Exception as exc:
        logger.warning("Source extraction failed for '%s': %s", article.url, exc)
        return article
