"""Draft notification helpers (Webhook + Telegram)."""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time

import httpx

import config

logger = logging.getLogger(__name__)
_WHATSAPP_TARGET_RE = re.compile(r"^\+?\d{8,15}$")


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


def _send_webhook(message: str, payload: dict, event: str = "draft_created") -> bool:
    if not config.NOTIFY_WEBHOOK_URL:
        return False
    sent = _post_json(
        config.NOTIFY_WEBHOOK_URL,
        {"text": message, "event": event, **payload},
    )
    if sent:
        logger.info("Notificación enviada por webhook.")
    return sent


def _send_telegram(message: str) -> bool:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        return False
    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram accepts at most 4096 characters. Exact prompt characters are
    # preserved across chunks so a long prompt is never silently truncated.
    chunks = [message[index : index + 3900] for index in range(0, len(message), 3900)]
    sent = True
    for chunk in chunks or [""]:
        sent = _post_json(
            url,
            {
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": chunk,
                "disable_web_page_preview": True,
            },
        ) and sent
        if not sent:
            break
    if sent:
        logger.info("Notificación enviada por Telegram.")
    return sent


def _resolve_whatsapp_target() -> str:
    configured = config.OPENCLAW_WHATSAPP_TARGET
    if configured:
        return configured if _WHATSAPP_TARGET_RE.fullmatch(configured) else ""
    try:
        result = subprocess.run(
            [
                config.OPENCLAW_CLI,
                "config",
                "get",
                "channels.whatsapp.allowFrom",
                "--json",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        values = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return ""
    if not isinstance(values, list) or len(values) != 1:
        return ""
    target = str(values[0]).strip()
    return target if _WHATSAPP_TARGET_RE.fullmatch(target) else ""


def _send_whatsapp(message: str, media_url: str = "") -> bool:
    """Send a private WhatsApp message without logging its target or payload."""
    target = _resolve_whatsapp_target()
    if not target:
        logger.warning(
            "WhatsApp no tiene un destinatario único; configura "
            "OPENCLAW_WHATSAPP_TARGET."
        )
        return False
    command = [
        config.OPENCLAW_CLI,
        "message",
        "send",
        "--channel",
        "whatsapp",
        "--target",
        target,
        "--message",
        message,
        "--json",
    ]
    if media_url:
        command.extend(["--media", media_url])
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("Falló WhatsApp (%s).", type(exc).__name__)
        return False
    if result.returncode != 0:
        logger.warning("Falló WhatsApp (exit=%d).", result.returncode)
        return False
    logger.info("Notificación enviada por WhatsApp.")
    return True


def _build_manual_image_message(
    *,
    job_id: str,
    title: str,
    alt_text: str,
    full_prompt: str,
    expected_path: str,
) -> str:
    return "\n".join(
        [
            "Portada manual pendiente",
            f"ID: {job_id}",
            f"Título: {title}",
            f"Texto alternativo: {alt_text}",
            "",
            "PROMPT EXACTO PARA CHATGPT:",
            full_prompt,
            "",
            "Guarda la imagen PNG, JPG o WEBP con este nombre:",
            expected_path,
            "",
            "Después ejecuta:",
            f"{config.BASE_DIR / 'process_manual_cover.sh'} {job_id}",
        ]
    )


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


def notify_manual_image_required(
    *,
    job_id: str,
    title: str,
    alt_text: str,
    full_prompt: str,
    expected_path: str,
) -> None:
    """Notify that a complete article package is waiting for its cover."""
    if not config.NOTIFICATIONS_ENABLED:
        return

    message = _build_manual_image_message(
        job_id=job_id,
        title=title,
        alt_text=alt_text,
        full_prompt=full_prompt,
        expected_path=expected_path,
    )
    payload = {
        "job_id": job_id,
        "title": title,
        "alt_text": alt_text,
        "full_prompt": full_prompt,
        "expected_path": expected_path,
    }
    channel_configured = bool(config.NOTIFY_WEBHOOK_URL) or bool(
        config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID
    )
    sent = False
    sent = _send_webhook(
        message,
        payload,
        event="manual_image_required",
    ) or sent
    sent = _send_telegram(message) or sent
    if not sent:
        if channel_configured:
            logger.warning(
                "Trabajo manual creado, pero falló la entrega por todos los canales."
            )
        else:
            logger.info(
                "Trabajo manual creado sin canal de notificación configurado."
            )


def notify_weekly_digest(
    *, message: str, posts: list[dict], period_label: str
) -> bool:
    """Deliver a WhatsApp-ready weekly digest through configured channels."""
    if not config.NOTIFICATIONS_ENABLED:
        logger.warning("Resumen semanal no enviado: notificaciones desactivadas.")
        return False

    payload = {
        "period": period_label,
        "post_count": len(posts),
        "posts": [
            {
                "id": item.get("id"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "url": item.get("url", ""),
            }
            for item in posts
        ],
    }
    sent = False
    sent = _send_webhook(message, payload, event="weekly_digest") or sent
    sent = _send_whatsapp(message) or sent
    if sent:
        logger.info("Resumen semanal enviado (%d publicaciones).", len(posts))
    else:
        logger.warning("Falló la entrega del resumen semanal por todos los canales.")
    return sent


def notify_daily_status_suggestion(
    *, message: str, image_url: str, post: dict
) -> bool:
    """Send one share-ready daily post privately through WhatsApp."""
    if not config.NOTIFICATIONS_ENABLED:
        logger.warning("Sugerencia diaria no enviada: notificaciones desactivadas.")
        return False
    sent = _send_whatsapp(message, media_url=image_url)
    if sent:
        logger.info(
            "Sugerencia diaria enviada por WhatsApp (post_id=%s).",
            post.get("id"),
        )
    return sent
