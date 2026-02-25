"""Validate and enrich post links before publishing."""

from __future__ import annotations

import logging
from html import escape
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

_SECTION_TITLES = {
    "publicaciones recientes",
    "recursos internos recomendados",
    "recursos externos recomendados",
    "fuente externa consultada",
}


def _is_public_http_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in ("http", "https"):
        return False
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    if host.endswith(".local"):
        return False
    return True


def _normalize_absolute_url(href: str) -> str:
    raw = (href or "").strip()
    if not raw:
        return ""
    if raw.startswith(("#", "mailto:", "tel:")):
        return raw
    if raw.startswith("/"):
        return urljoin(config.WP_SITE_URL.rstrip("/") + "/", raw.lstrip("/"))
    if not urlparse(raw).netloc:
        return urljoin(config.WP_SITE_URL.rstrip("/") + "/", raw)
    return raw


def _is_internal_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    site = (config.WP_SITE_DOMAIN or "").lower()
    if not site:
        return False
    return host == site or host.endswith(f".{site}")


def _canonical_internal_key(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "/").rstrip("/") or "/"
    return f"{parsed.netloc.lower()}{path}"


def _check_url_ok(url: str, cache: dict[str, bool], timeout: int) -> bool:
    if url in cache:
        return cache[url]
    if not _is_public_http_url(url):
        cache[url] = False
        return False
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.head(url)
            if not (200 <= resp.status_code < 400):
                resp = client.get(url)
            ok = 200 <= resp.status_code < 400
    except Exception:
        ok = False
    cache[url] = ok
    return ok


def _remove_existing_sections(soup: BeautifulSoup) -> None:
    for heading in soup.find_all(["h2", "h3"]):
        text = " ".join(heading.get_text(" ", strip=True).lower().split())
        if text not in _SECTION_TITLES:
            continue
        to_remove = []
        following = heading.next_sibling
        while following is not None:
            next_node = following.next_sibling
            tag_name = getattr(following, "name", "")
            if tag_name in {"h2", "h3"}:
                break
            to_remove.append(following)
            following = next_node
        heading.decompose()
        for node in to_remove:
            if hasattr(node, "decompose"):
                node.decompose()
            else:
                node.extract()


def _build_internal_fallback_html(urls: list[str]) -> str:
    if not urls:
        return ""
    items = []
    for raw in urls:
        clean = (raw or "").strip()
        if not clean:
            continue
        parsed = urlparse(clean)
        domain = (parsed.netloc or "").replace("www.", "")
        path = (parsed.path or "").strip("/")
        if path:
            label = path.replace("-", " ").replace("/", " ").title()[:80]
        else:
            label = f"Portal {domain}" if domain else "Recurso interno"
        items.append(f'<li><a href="{escape(clean, quote=True)}">{escape(label)}</a></li>')
    if not items:
        return ""
    return (
        "<h2>Recursos Internos Recomendados</h2>"
        "<ul>"
        + "".join(items)
        + "</ul>"
    )


def _build_recent_gallery_html(posts: list[dict]) -> str:
    if not posts:
        return ""
    cards: list[str] = []
    for post in posts:
        title = escape(str(post.get("title", "")).strip())
        url = escape(str(post.get("url", "")).strip(), quote=True)
        if not title or not url:
            continue
        image_url = str(post.get("image_url", "")).strip()
        image_alt = escape(str(post.get("image_alt", "")).strip() or title)
        image_html = ""
        if image_url:
            image_html = (
                f'<img src="{escape(image_url, quote=True)}" alt="{image_alt}" '
                'loading="lazy" style="width:100%;height:auto;border-radius:8px;margin-bottom:8px;" />'
            )
        cards.append(
            (
                '<article style="border:1px solid #ddd;border-radius:10px;padding:10px;">'
                f'<a href="{url}" style="text-decoration:none;">'
                f"{image_html}<strong>{title}</strong>"
                "</a></article>"
            )
        )
    if not cards:
        return ""
    return (
        "<h2>Publicaciones Recientes</h2>"
        '<div class="recent-posts-gallery" '
        'style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;">'
        + "".join(cards)
        + "</div>"
    )


def _build_preferred_external_html(url: str) -> str:
    clean = (url or "").strip()
    if not clean:
        return ""
    domain = (urlparse(clean).netloc or clean).replace("www.", "")
    return (
        "<h2>Recursos Externos Recomendados</h2>"
        "<ul>"
        f'<li><a href="{escape(clean, quote=True)}">{escape(domain)}</a></li>'
        "</ul>"
    )


def sanitize_and_enrich_body(
    *,
    html: str,
    source_url: str = "",
    recent_posts: list[dict] | None = None,
    preferred_external_url: str = "",
) -> tuple[str, dict]:
    """Remove broken links and append reliable internal/external sections."""
    soup = BeautifulSoup(html or "", "html.parser")
    _remove_existing_sections(soup)

    link_cache: dict[str, bool] = {}
    internal_count = 0
    external_count = 0
    removed_links = 0
    external_domains: set[str] = set()
    trusted_internal_urls: set[str] = set()

    site_home = _normalize_absolute_url(config.WP_SITE_URL)
    if site_home and _is_internal_url(site_home):
        trusted_internal_urls.add(_canonical_internal_key(site_home))
    for raw in config.INTERNAL_LINKS:
        normalized = _normalize_absolute_url(raw)
        if normalized and _is_internal_url(normalized):
            trusted_internal_urls.add(_canonical_internal_key(normalized))
    for recent in recent_posts or []:
        normalized = _normalize_absolute_url(str(recent.get("url", "")).strip())
        if normalized and _is_internal_url(normalized):
            trusted_internal_urls.add(_canonical_internal_key(normalized))

    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        normalized = _normalize_absolute_url(href)
        if not normalized:
            anchor.unwrap()
            removed_links += 1
            continue
        if normalized.startswith(("#", "mailto:", "tel:")):
            continue

        is_internal = _is_internal_url(normalized)
        if is_internal:
            if trusted_internal_urls and _canonical_internal_key(normalized) not in trusted_internal_urls:
                anchor.unwrap()
                removed_links += 1
                continue
            anchor["href"] = normalized
            internal_count += 1
            continue

        is_ok = True
        if config.LINK_VALIDATION_ENABLED:
            is_ok = _check_url_ok(normalized, link_cache, config.LINK_CHECK_TIMEOUT)
        if not is_ok:
            anchor.unwrap()
            removed_links += 1
            continue

        anchor["href"] = normalized
        external_count += 1
        domain = (urlparse(normalized).netloc or "").lower()
        if domain:
            external_domains.add(domain)

    valid_recent_posts: list[dict] = []
    for recent in recent_posts or []:
        raw_url = str(recent.get("url", "")).strip()
        if not raw_url:
            continue
        normalized_url = _normalize_absolute_url(raw_url)
        if not normalized_url or not _is_internal_url(normalized_url):
            continue
        clean_recent = dict(recent)
        clean_recent["url"] = normalized_url
        image_url = str(clean_recent.get("image_url", "")).strip()
        if image_url:
            image_ok = True
            if config.LINK_VALIDATION_ENABLED:
                image_ok = _check_url_ok(image_url, link_cache, config.LINK_CHECK_TIMEOUT)
            if not image_ok:
                clean_recent["image_url"] = ""
        valid_recent_posts.append(clean_recent)

    gallery_html = _build_recent_gallery_html(valid_recent_posts)
    if gallery_html:
        soup.append(BeautifulSoup(gallery_html, "html.parser"))
        internal_count += len(valid_recent_posts)

    fallback_internal_count = 0
    if internal_count == 0:
        fallback_links: list[str] = []
        for raw in config.INTERNAL_LINKS:
            normalized = _normalize_absolute_url(raw)
            if not normalized or not _is_internal_url(normalized):
                continue
            fallback_links.append(normalized)
            if len(fallback_links) >= 3:
                break
        fallback_html = _build_internal_fallback_html(fallback_links)
        if fallback_html:
            soup.append(BeautifulSoup(fallback_html, "html.parser"))
            internal_count += len(fallback_links)
            fallback_internal_count = len(fallback_links)

    if source_url and _is_public_http_url(source_url):
        source_domain = (urlparse(source_url).netloc or "").lower()
        source_ok = True
        if config.LINK_VALIDATION_ENABLED:
            source_ok = _check_url_ok(source_url, link_cache, config.LINK_CHECK_TIMEOUT)
        if source_ok and source_domain not in external_domains and external_count == 0:
            source_html = (
                "<h2>Fuente Externa Consultada</h2>"
                "<p>"
                f'<a href="{escape(source_url, quote=True)}">{escape(source_domain)}</a>'
                "</p>"
            )
            soup.append(BeautifulSoup(source_html, "html.parser"))
            external_count += 1
            external_domains.add(source_domain)

    if preferred_external_url:
        preferred_domain = (urlparse(preferred_external_url).netloc or "").lower()
        preferred_ok = True
        if config.LINK_VALIDATION_ENABLED:
            preferred_ok = _check_url_ok(preferred_external_url, link_cache, config.LINK_CHECK_TIMEOUT)
        if preferred_ok and preferred_domain and preferred_domain not in external_domains:
            external_html = _build_preferred_external_html(preferred_external_url)
            soup.append(BeautifulSoup(external_html, "html.parser"))
            external_count += 1
            preferred_added = True
        else:
            preferred_added = False
    else:
        preferred_added = False

    return str(soup), {
        "internal_links": internal_count,
        "external_links": external_count,
        "removed_links": removed_links,
        "gallery_links": len(valid_recent_posts),
        "fallback_internal_links": fallback_internal_count,
        "preferred_external_added": preferred_added,
    }
