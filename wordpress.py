"""Cliente REST API de WordPress: sube media y crea borradores."""

import base64
import hashlib
import logging
import re
import random
import time
import unicodedata
from html import unescape
from pathlib import Path
from urllib.parse import urljoin
from urllib.parse import quote, urlparse

import httpx

import config
from content import GeneratedPost

logger = logging.getLogger(__name__)
_AUTHOR_CACHE: dict[str, int] = {}
_SG_REFRESH_RE = re.compile(r'content="0;([^"]+)"', re.IGNORECASE)
_SG_CHALLENGE_RE = re.compile(r'const sgchallenge="([^"]+)";')
_SG_SUBMIT_RE = re.compile(r'const sgsubmit_url="([^"]+)";')


def _int_to_min_be(value: int) -> bytes:
    if value <= 0xFF:
        return bytes([value])
    if value <= 0xFFFF:
        return value.to_bytes(2, "big")
    if value <= 0xFFFFFF:
        return value.to_bytes(3, "big")
    return value.to_bytes(4, "big")


def _solve_sgchallenge(challenge: str, start: int, max_iters: int = 8_000_000) -> tuple[str, int, float] | None:
    """Solve SiteGuard PoW challenge and return solution, hashes, elapsed seconds."""
    try:
        complexity = int(challenge.split(":", 1)[0])
    except Exception:
        return None
    if complexity <= 0 or complexity > 31:
        return None

    challenge_bytes = challenge.encode("utf-8")
    shift = 32 - complexity
    t0 = time.time()

    for idx in range(max_iters):
        counter = start + idx
        payload = challenge_bytes + _int_to_min_be(counter)
        digest = hashlib.sha1(payload).digest()
        if (int.from_bytes(digest[:4], "big") >> shift) == 0:
            solution = base64.b64encode(payload).decode("ascii")
            return solution, idx + 1, max(time.time() - t0, 0.001)
    return None


def _is_sgcaptcha_html(resp: httpx.Response) -> bool:
    ctype = (resp.headers.get("content-type") or "").lower()
    if resp.status_code != 202:
        return False
    if "text/html" not in ctype:
        return False
    text = (resp.text or "").lower()
    return ".well-known/sgcaptcha" in text or "robot challenge screen" in text


def _try_solve_sgcaptcha(client: httpx.Client, endpoint_url: str, resp: httpx.Response) -> bool:
    """Attempt to solve SiteGuard challenge in-band for this client session."""
    refresh_match = _SG_REFRESH_RE.search(resp.text or "")
    if not refresh_match:
        return False
    refresh_url = urljoin(config.WP_SITE_URL + "/", unescape(refresh_match.group(1)))

    try:
        challenge_resp = client.get(refresh_url)
    except Exception:
        return False
    if challenge_resp.status_code >= 400:
        parsed = urlparse(endpoint_url)
        path_query = parsed.path
        if parsed.query:
            path_query = f"{path_query}?{parsed.query}"
        fallback_refresh = urljoin(
            config.WP_SITE_URL + "/",
            f"/.well-known/sgcaptcha/?r={quote(path_query, safe='')}",
        )
        try:
            challenge_resp = client.get(fallback_refresh)
        except Exception:
            return False
        if challenge_resp.status_code >= 400:
            logger.warning("No se pudo abrir challenge sgcaptcha para %s", endpoint_url)
            return False
    challenge_html = challenge_resp.text or ""
    challenge_match = _SG_CHALLENGE_RE.search(challenge_html)
    submit_match = _SG_SUBMIT_RE.search(challenge_html)
    if not challenge_match or not submit_match:
        return False

    challenge = challenge_match.group(1)
    submit_url = urljoin(config.WP_SITE_URL + "/", unescape(submit_match.group(1)))
    start_from = random.randint(0, 40_000_000)
    solved = _solve_sgchallenge(challenge, start=start_from)
    if not solved:
        logger.warning("No se pudo resolver sgcaptcha para %s", endpoint_url)
        return False
    solution, hashes, elapsed = solved
    sep = "&" if "?" in submit_url else "?"
    token_url = f"{submit_url}{sep}sol={solution}&s={int(elapsed * 1000)}:{hashes}"
    try:
        client.get(token_url)
    except Exception:
        return False

    verify = client.get(endpoint_url)
    if _is_sgcaptcha_html(verify):
        logger.warning("sgcaptcha persistió para %s", endpoint_url)
        return False
    logger.info("sgcaptcha resuelto para %s (hashes=%d)", endpoint_url, hashes)
    return True


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


def _normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9\s-]", " ", value).lower()
    return re.sub(r"\s+", " ", value).strip()


def _request(
    method: str, endpoint: str, retry_on_500: bool = True, **kwargs
) -> httpx.Response | None:
    """Make an authenticated WP REST API request."""
    url = _api_url(endpoint)
    with httpx.Client(timeout=60, auth=_auth()) as client:
        try:
            resp = getattr(client, method)(url, **kwargs)
            if _is_sgcaptcha_html(resp):
                solved = _try_solve_sgcaptcha(client, url, resp)
                if solved:
                    resp = getattr(client, method)(url, **kwargs)
            if _is_sgcaptcha_html(resp):
                logger.error("WordPress blocked by sgcaptcha: %s %s", method.upper(), url)
                return None
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


def _resolve_author_id(author_name: str) -> int | None:
    """Resolve WordPress user ID from display name/slug."""
    clean_name = " ".join((author_name or "").split())
    if not clean_name:
        return None

    key = _normalize_name(clean_name)
    if key in _AUTHOR_CACHE:
        return _AUTHOR_CACHE[key]

    resp = _request(
        "get",
        "users",
        params={"search": clean_name, "per_page": 100},
        retry_on_500=False,
    )
    if not resp:
        logger.warning("No se pudo resolver autor '%s' (users endpoint no disponible).", clean_name)
        return None

    try:
        users = resp.json()
    except Exception:
        logger.warning("Respuesta inválida al resolver autor '%s'.", clean_name)
        return None
    if not isinstance(users, list) or not users:
        logger.warning("No se encontró autor en WordPress con nombre '%s'.", clean_name)
        return None

    exact_match = None
    fallback_match = None
    for user in users:
        values = [
            str(user.get("name", "")),
            str(user.get("slug", "")),
            str(user.get("username", "")),
            str(user.get("nickname", "")),
        ]
        normalized_values = [_normalize_name(v) for v in values if v]
        if key in normalized_values:
            exact_match = user
            break
        if fallback_match is None and any(key in nv for nv in normalized_values):
            fallback_match = user

    chosen = exact_match or fallback_match
    if not chosen:
        logger.warning("No hubo coincidencia de autor para '%s'.", clean_name)
        return None

    try:
        author_id = int(chosen["id"])
    except Exception:
        logger.warning("El usuario encontrado para '%s' no tiene ID válido.", clean_name)
        return None

    _AUTHOR_CACHE[key] = author_id
    logger.info("Autor '%s' resuelto a user_id=%d", clean_name, author_id)
    return author_id


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
        "og_title": post.og_title or post.seo_title,
        "og_description": post.og_description or post.seo_description,
        "twitter_title": post.twitter_title or post.seo_title,
        "twitter_description": post.twitter_description or post.seo_description,
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


def list_recent_published_posts(limit: int = 6, exclude_ids: set[int] | None = None) -> list[dict]:
    """Return recent published posts with canonical link and optional featured image."""
    if limit <= 0:
        return []
    exclude_ids = exclude_ids or set()
    per_page = max(1, min(limit * 3, 30))
    params = {
        "status": "publish",
        "orderby": "date",
        "order": "desc",
        "per_page": per_page,
        "_embed": "wp:featuredmedia",
    }
    resp = _request("get", "posts", params=params, retry_on_500=False)
    if not resp:
        return []

    posts: list[dict] = []
    for item in resp.json():
        try:
            post_id = int(item.get("id"))
        except Exception:
            continue
        if post_id in exclude_ids:
            continue
        link = str(item.get("link", "")).strip()
        raw_title = str(item.get("title", {}).get("rendered", "")).strip()
        title = unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
        if not link or not title:
            continue

        image_url = ""
        image_alt = ""
        embedded = item.get("_embedded", {})
        media_list = embedded.get("wp:featuredmedia", []) if isinstance(embedded, dict) else []
        if isinstance(media_list, list) and media_list:
            media = media_list[0] or {}
            image_url = str(media.get("source_url", "")).strip()
            image_alt = str(media.get("alt_text", "")).strip()

        posts.append(
            {
                "id": post_id,
                "url": link,
                "title": title,
                "image_url": image_url,
                "image_alt": image_alt,
            }
        )
        if len(posts) >= limit:
            break
    return posts


def create_draft(
    post: GeneratedPost, media_id: int | None = None, author_name: str = ""
) -> int | None:
    """Create a WordPress draft post. Returns post ID."""
    category_ids = _resolve_terms("categories", post.categories)
    tag_ids = _resolve_terms("tags", post.tags)
    author_id = _resolve_author_id(author_name)

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
    if author_id:
        payload["author"] = author_id
    elif author_name:
        logger.warning(
            "No se pudo asignar autor '%s'. Se publicará con el autor por defecto de la API.",
            author_name,
        )

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
