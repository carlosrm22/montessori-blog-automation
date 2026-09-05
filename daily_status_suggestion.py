"""Envía por WhatsApp una publicación diaria lista para compartir como Estado."""

from __future__ import annotations

import argparse
import logging
import re
import sys

import config
import state
from notifier import notify_daily_status_suggestion
from wordpress import RecentPostsUnavailable, list_recent_published_posts

logger = logging.getLogger(__name__)


def _clean(value: str) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text.translate(str.maketrans({"*": "", "_": "", "~": ""}))


def _short_description(value: str, max_len: int = 120) -> str:
    """Return one compact, WhatsApp-safe description for the selected post."""
    text = _clean(value)
    if not text:
        return "Una lectura para acompañar la reflexión y la práctica educativa."
    sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    candidate = sentence if len(sentence) >= 60 else text
    if len(candidate) <= max_len:
        return candidate
    shortened = candidate[: max_len - 1].rsplit(" ", 1)[0].rstrip(".,;: ")
    return f"{shortened or candidate[: max_len - 1]}…"


def select_post(posts: list[dict], history: dict[int, str]) -> dict | None:
    """Prefer never-sent recent posts, then the least-recently sent one."""
    if not posts:
        return None
    for post in posts:
        if post.get("id") not in history:
            return post
    return min(posts, key=lambda post: history.get(int(post["id"]), ""))


def build_status_message(post: dict) -> str:
    title = _clean(str(post.get("title", "")))
    description = _short_description(str(post.get("description", "")))
    url = str(post.get("url", "")).strip()
    return "\n".join(
        [
            url,
            f"*{title}*",
            description,
        ]
    )


def run(*, dry_run: bool = False) -> bool:
    try:
        posts = list_recent_published_posts(limit=100)
    except RecentPostsUnavailable:
        logger.error("No se pudieron consultar publicaciones para la sugerencia diaria.")
        return False
    post = select_post(posts, state.get_daily_share_history())
    if post is None:
        logger.info("No hay publicaciones disponibles para sugerir.")
        return True
    message = build_status_message(post)
    image_url = str(post.get("image_url", "")).strip()
    if dry_run:
        print(message)
        print(f"\nPortada: {image_url or 'sin portada'}")
        return True
    if not notify_daily_status_suggestion(
        message=message, image_url=image_url, post=post
    ):
        return False
    state.mark_daily_share_sent(
        int(post["id"]), str(post.get("url", "")), str(post.get("title", ""))
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Sugerencia diaria para Estado")
    parser.add_argument("--dry-run", action="store_true", help="No envía ni registra")
    args = parser.parse_args()
    config.setup_logging()
    if not config.WP_SITE_URL or not config.WP_USERNAME or not config.WP_APP_PASSWORD:
        logger.error("Falta configuración de WordPress.")
        sys.exit(1)
    if not run(dry_run=args.dry_run):
        sys.exit(1)


if __name__ == "__main__":
    main()
