"""Draft notification helpers (Webhook + Telegram)."""

from __future__ import annotations

import logging

import httpx

import config

logger = logging.getLogger(__name__)


def _build_message(
    *,
    post_id: int,
    title: str,
    topic_name: str,
    author_name: str,
    edit_url: str,
    truseo_score: int | None,
    headline_score: int | None,
) -> str:
    lines = [
        "Nuevo borrador generado",
        f"Título: {title}",
        f"Tema: {topic_name}",
        f"Autor: {author_name or 'N/A'}",
        f"Post ID: {post_id}",
    ]
    if truseo_score is not None or headline_score is not None:
        lines.append(f"SEO: TruSEO-like={truseo_score} | Headline={headline_score}")
    lines.append(f"Editar: {edit_url}")
    return "\n".join(lines)


def _send_webhook(message: str, payload: dict) -> bool:
    if not config.NOTIFY_WEBHOOK_URL:
        return False
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                config.NOTIFY_WEBHOOK_URL,
                json={"text": message, "event": "draft_created", **payload},
            )
            resp.raise_for_status()
        logger.info("Notificación enviada por webhook.")
        return True
    except Exception as exc:
        logger.warning("Falló notificación webhook: %s", exc)
        return False


def _send_telegram(message: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.post(
                url,
                json={
                    "chat_id": config.TELEGRAM_CHAT_ID,
                    "text": message,
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()
        logger.info("Notificación enviada por Telegram.")
        return True
    except Exception as exc:
        logger.warning("Falló notificación Telegram: %s", exc)
        return False


def notify_draft_created(
    *,
    post_id: int,
    title: str,
    topic_name: str,
    author_name: str,
    edit_url: str,
    truseo_score: int | None = None,
    headline_score: int | None = None,
) -> None:
    if not config.NOTIFICATIONS_ENABLED:
        return

    message = _build_message(
        post_id=post_id,
        title=title,
        topic_name=topic_name,
        author_name=author_name,
        edit_url=edit_url,
        truseo_score=truseo_score,
        headline_score=headline_score,
    )
    payload = {
        "post_id": post_id,
        "title": title,
        "topic_name": topic_name,
        "author_name": author_name,
        "edit_url": edit_url,
        "truseo_score": truseo_score,
        "headline_score": headline_score,
    }
    sent = False
    sent = _send_webhook(message, payload) or sent
    sent = _send_telegram(message) or sent
    if not sent:
        logger.info(
            "Borrador creado, pero no hay canal de notificación configurado. "
            "Define NOTIFY_WEBHOOK_URL o TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID."
        )

