"""Draft notification helpers (Webhook + Telegram)."""

from __future__ import annotations

import logging
import time

import httpx

import config

logger = logging.getLogger(__name__)


def _post_json(url: str, payload: dict, attempts: int = 3) -> bool:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            with httpx.Client(timeout=20) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
            return True
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    logger.warning(
        "Falló notificación HTTP después de %d intentos (%s).",
        attempts,
        type(last_error).__name__ if last_error else "error desconocido",
    )
    return False


def _build_message(
    *,
    post_id: int,
    title: str,
    topic_name: str,
    author_name: str,
    edit_url: str,
    truseo_score: int | None,
    headline_score: int | None,
    conversion_intent: str = "editorial",
    commercial_relevance: str = "low",
    destination_url: str = "",
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
    lines.append(f"Conversión: {conversion_intent} / {commercial_relevance}")
    if destination_url:
        lines.append(f"Destino: {destination_url}")
    lines.append(f"Editar: {edit_url}")
    return "\n".join(lines)


def _send_webhook(message: str, payload: dict) -> bool:
    if not config.NOTIFY_WEBHOOK_URL:
        return False
    sent = _post_json(
        config.NOTIFY_WEBHOOK_URL,
        {"text": message, "event": "draft_created", **payload},
    )
    if sent:
        logger.info("Notificación enviada por webhook.")
    return sent


def _send_telegram(message: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    sent = _post_json(
        url,
        {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        },
    )
    if sent:
        logger.info("Notificación enviada por Telegram.")
    return sent


def notify_draft_created(
    *,
    post_id: int,
    title: str,
    topic_name: str,
    author_name: str,
    edit_url: str,
    truseo_score: int | None = None,
    headline_score: int | None = None,
    conversion_intent: str = "editorial",
    commercial_relevance: str = "low",
    destination_url: str = "",
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
        conversion_intent=conversion_intent,
        commercial_relevance=commercial_relevance,
        destination_url=destination_url,
    )
    payload = {
        "post_id": post_id,
        "title": title,
        "topic_name": topic_name,
        "author_name": author_name,
        "edit_url": edit_url,
        "truseo_score": truseo_score,
        "headline_score": headline_score,
        "conversion_intent": conversion_intent,
        "commercial_relevance": commercial_relevance,
        "destination_url": destination_url,
    }
    channel_configured = bool(config.NOTIFY_WEBHOOK_URL) or bool(
        config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID
    )
    sent = False
    sent = _send_webhook(message, payload) or sent
    sent = _send_telegram(message) or sent
    if not sent:
        if channel_configured:
            logger.warning(
                "Borrador creado y registrado, pero falló la entrega por todos "
                "los canales configurados."
            )
        else:
            logger.info(
                "Borrador creado, pero no hay canal de notificación configurado. "
                "Define NOTIFY_WEBHOOK_URL o TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID."
            )
