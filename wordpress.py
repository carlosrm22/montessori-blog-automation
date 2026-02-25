"""Cliente REST API de WordPress: sube media y crea borradores."""

import logging
import time
from pathlib import Path

import httpx

import config
from content import GeneratedPost

logger = logging.getLogger(__name__)


def _auth() -> tuple[str, str]:
    return (config.WP_USERNAME, config.WP_APP_PASSWORD)


def _api_url(endpoint: str) -> str:
    return f"{config.WP_SITE_URL}/wp-json/wp/v2/{endpoint}"


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


def upload_media(image_path: Path, title: str = "Blog cover") -> int | None:
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
        return media_id
    return None


def create_draft(
    post: GeneratedPost, media_id: int | None = None
) -> int | None:
    """Create a WordPress draft post. Returns post ID."""
    category_ids = _resolve_terms("categories", post.categories)
    tag_ids = _resolve_terms("tags", post.tags)

    payload: dict = {
        "title": post.title,
        "content": post.body,
        "excerpt": post.excerpt,
        "status": "draft",
        "categories": category_ids,
        "tags": tag_ids,
    }
    if media_id:
        payload["featured_media"] = media_id

    resp = _request("post", "posts", json=payload)
    if resp:
        post_id = resp.json()["id"]
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
