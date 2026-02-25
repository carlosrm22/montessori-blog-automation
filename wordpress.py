"""Cliente REST API de WordPress: sube media y crea borradores."""

import logging
import re
import time
import unicodedata
from pathlib import Path

import httpx

import config
from content import GeneratedPost

logger = logging.getLogger(__name__)


def _auth() -> tuple[str, str]:
    return (config.WP_USERNAME, config.WP_APP_PASSWORD)


def _api_url(endpoint: str) -> str:
    return f"{config.WP_SITE_URL}/wp-json/wp/v2/{endpoint}"


def _aioseo_url(endpoint: str) -> str:
    return f"{config.WP_SITE_URL}/wp-json/aioseo/v1/{endpoint}"


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9\s-]", "", normalized).strip().lower()
    slug = re.sub(r"[-\s]+", "-", normalized).strip("-")
    return slug[:90]


def _truncate(text: str, max_len: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= max_len:
        return text
    return text[:max_len].rsplit(" ", 1)[0] or text[:max_len]


def _request(
    method: str, endpoint: str, retry_on_500: bool = True, **kwargs
) -> httpx.Response | None:
    """Make an authenticated WP REST API request."""
    url = _api_url(endpoint)
    with httpx.Client(timeout=60, auth=_auth()) as client:
        try:
            resp = getattr(client, method)(url, **kwargs)
            if resp.status_code == 401:
                logger.error("WordPress auth failed (401). Check credentials.")
                return None
            if resp.status_code >= 500 and retry_on_500:
                logger.warning("WordPress 500 error, retrying once in 5s...")
                time.sleep(5)
                resp = getattr(client, method)(url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            logger.error("WordPress API error: %s %s -> %s", method.upper(), url, exc)
            return None
        except httpx.RequestError as exc:
            logger.error("WordPress request failed: %s", exc)
            return None


def _aioseo_request(
    method: str, endpoint: str, retry_on_500: bool = False, **kwargs
) -> httpx.Response | None:
    """Make an authenticated AIOSEO REST API request."""
    url = _aioseo_url(endpoint)
    with httpx.Client(timeout=60, auth=_auth()) as client:
        try:
            resp = getattr(client, method)(url, **kwargs)
            if resp.status_code >= 500 and retry_on_500:
                logger.warning("AIOSEO API 500, retrying once in 5s...")
                time.sleep(5)
                resp = getattr(client, method)(url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            logger.warning("AIOSEO API error: %s %s -> %s", method.upper(), url, exc)
            return None
        except httpx.RequestError as exc:
            logger.warning("AIOSEO request failed: %s", exc)
            return None


def _resolve_or_create_term(taxonomy: str, name: str) -> int | None:
    """Find existing term by name or create it. Returns term ID."""
    # Search existing
    resp = _request("get", taxonomy, params={"search": name, "per_page": 100})
    if resp:
        for term in resp.json():
            if term["name"].lower() == name.lower():
                return term["id"]
    # Create new
    resp = _request("post", taxonomy, json={"name": name})
    if resp:
        term_id = resp.json()["id"]
        logger.info("Created %s '%s' (id=%d)", taxonomy, name, term_id)
        return term_id
    return None


def _resolve_terms(taxonomy: str, names: list[str]) -> list[int]:
    """Resolve a list of term names to IDs."""
    ids = []
    for name in names:
        term_id = _resolve_or_create_term(taxonomy, name.strip())
        if term_id:
            ids.append(term_id)
    return ids


def _update_media_metadata(
    media_id: int,
    title: str,
    alt_text: str = "",
    caption: str = "",
    description: str = "",
) -> None:
    payload = {
        "title": _truncate(title, 120),
        "alt_text": _truncate(alt_text, 125),
        "caption": _truncate(caption, 220),
        "description": _truncate(description, 400),
    }
    resp = _request("post", f"media/{media_id}", json=payload, retry_on_500=False)
    if resp:
        logger.info("Media metadata updated for id=%d", media_id)
    else:
        logger.warning("Could not update metadata for media id=%d", media_id)


def upload_media(
    image_path: Path,
    title: str = "Blog cover",
    alt_text: str = "",
    caption: str = "",
    description: str = "",
) -> int | None:
    """Upload image to WP media library. Returns media ID."""
    mime = "image/jpeg" if image_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    with open(image_path, "rb") as f:
        data = f.read()

    filename = image_path.name
    resp = _request(
        "post", "media",
        content=data,
        headers={
            "Content-Type": mime,
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
    if resp:
        media_id = resp.json()["id"]
        logger.info("Media uploaded: id=%d, file=%s", media_id, filename)
        _update_media_metadata(
            media_id,
            title=title,
            alt_text=alt_text or title,
            caption=caption or title,
            description=description or caption or title,
        )
        return media_id
    return None


def _sync_aioseo(post_id: int, post: GeneratedPost) -> None:
    """Push SEO metadata to AIOSEO if available."""
    if not config.AIOSEO_SYNC:
        return

    keyword_candidates = [post.focus_keyphrase, *post.tags]
    keywords: list[str] = []
    seen: set[str] = set()
    for kw in keyword_candidates:
        k = " ".join((kw or "").split())
        if not k:
            continue
        key = k.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(k)
        if len(keywords) >= 8:
            break

    payload = {
        "id": post_id,
        "title": post.seo_title,
        "description": post.seo_description,
        "og_title": post.seo_title,
        "og_description": post.seo_description,
        "twitter_title": post.seo_title,
        "twitter_description": post.seo_description,
        "keywords": ", ".join(keywords),
    }
    resp = _aioseo_request("post", "post", json=payload)
    if not resp:
        logger.warning("AIOSEO sync failed for post id=%d", post_id)
        return
    try:
        data = resp.json()
        if data.get("success"):
            logger.info("AIOSEO metadata synced for post id=%d", post_id)
        else:
            logger.warning("AIOSEO sync returned non-success for post id=%d: %s", post_id, data)
    except Exception:
        logger.warning("AIOSEO sync response parse failed for post id=%d", post_id)


def create_draft(
    post: GeneratedPost, media_id: int | None = None
) -> int | None:
    """Create a WordPress draft post. Returns post ID."""
    category_ids = _resolve_terms("categories", post.categories)
    tag_ids = _resolve_terms("tags", post.tags)

    payload: dict = {
        "title": post.title,
        "content": post.body,
        "excerpt": post.excerpt or post.seo_description,
        "status": "draft",
        "categories": category_ids,
        "tags": tag_ids,
        "slug": _slugify(post.seo_title or post.title),
    }
    if media_id:
        payload["featured_media"] = media_id

    resp = _request("post", "posts", json=payload)
    if resp:
        post_id = resp.json()["id"]
        _sync_aioseo(post_id, post)
        logger.info("Draft created: id=%d, title='%s'", post_id, post.title)
        return post_id
    return None


if __name__ == "__main__":
    config.setup_logging()
    config.validate()
    # Test: list recent posts
    resp = _request("get", "posts", params={"per_page": 3, "status": "any"})
    if resp:
        for p in resp.json():
            print(f"  [{p['status']}] {p['id']}: {p['title']['rendered']}")
    else:
        print("Could not connect to WordPress API")
