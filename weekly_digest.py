"""Resumen semanal ligero de publicaciones, listo para compartir en WhatsApp."""

from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import config
from notifier import notify_weekly_digest
from wordpress import RecentPostsUnavailable, list_published_posts_between

logger = logging.getLogger(__name__)

_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def week_window(now: datetime, timezone_name: str) -> tuple[datetime, datetime]:
    """Return Monday 00:00 through now in the configured local timezone."""
    zone = ZoneInfo(timezone_name)
    local_now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
    start = (local_now - timedelta(days=local_now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return start, local_now


def _clean_whatsapp_text(value: str) -> str:
    """Remove HTML/spacing and markup characters that could break WhatsApp bold."""
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text.translate(str.maketrans({"*": "", "_": "", "~": ""}))


def _truncate(value: str, max_len: int) -> str:
    text = _clean_whatsapp_text(value)
    if len(text) <= max_len:
        return text
    shortened = text[: max_len - 1].rsplit(" ", 1)[0].rstrip(".,;: ")
    return f"{shortened or text[: max_len - 1]}…"


def _period_label(start: datetime, end: datetime) -> str:
    if start.year == end.year:
        if start.month == end.month:
            return f"{start.day} al {end.day} de {_MONTHS[end.month - 1]} de {end.year}"
        return (
            f"{start.day} de {_MONTHS[start.month - 1]} al "
            f"{end.day} de {_MONTHS[end.month - 1]} de {end.year}"
        )
    return (
        f"{start.day} de {_MONTHS[start.month - 1]} de {start.year} al "
        f"{end.day} de {_MONTHS[end.month - 1]} de {end.year}"
    )


def build_whatsapp_digest(
    posts: list[dict], start: datetime, end: datetime, description_max_len: int
) -> tuple[str, str]:
    """Build a compact plain-text message using WhatsApp-compatible markup."""
    period = _period_label(start, end)
    lines = ["📚 *Publicaciones de la semana*", f"_{period}_", ""]
    if not posts:
        lines.append("Esta semana no hubo publicaciones nuevas.")
        return "\n".join(lines), period

    for index, post in enumerate(posts, start=1):
        title = _clean_whatsapp_text(str(post.get("title", "")))
        description = _truncate(
            str(post.get("description", "")), description_max_len
        )
        url = str(post.get("url", "")).strip()
        lines.append(f"{index}. *{title}*")
        if description:
            lines.append(description)
        lines.append(f"🔗 {url}")
        lines.append("")
    lines.append("¡Gracias por leer y compartir!")
    return "\n".join(lines), period


def run(*, dry_run: bool = False, now: datetime | None = None) -> bool:
    try:
        start, end = week_window(
            now or datetime.now(timezone.utc), config.WEEKLY_DIGEST_TIMEZONE
        )
    except ZoneInfoNotFoundError:
        logger.error(
            "Zona horaria inválida para el resumen: %s",
            config.WEEKLY_DIGEST_TIMEZONE,
        )
        return False

    # WordPress expects UTC ISO-8601 timestamps for unambiguous date filtering.
    after = start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    before = end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    try:
        posts = list_published_posts_between(after=after, before=before)
    except RecentPostsUnavailable:
        logger.error("No se pudo consultar el historial semanal de WordPress.")
        return False

    message, period = build_whatsapp_digest(
        posts, start, end, config.WEEKLY_DIGEST_DESCRIPTION_MAX_LEN
    )
    if dry_run:
        print(message)
        return True
    return notify_weekly_digest(message=message, posts=posts, period_label=period)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resumen semanal para WhatsApp")
    parser.add_argument(
        "--dry-run", action="store_true", help="Muestra el resumen sin enviarlo"
    )
    args = parser.parse_args()
    config.setup_logging()
    if not config.WP_SITE_URL or not config.WP_USERNAME or not config.WP_APP_PASSWORD:
        logger.error("Falta configuración de WordPress para generar el resumen.")
        sys.exit(1)
    if not 80 <= config.WEEKLY_DIGEST_DESCRIPTION_MAX_LEN <= 300:
        logger.error("Longitud de descripción semanal fuera del rango 80-300.")
        sys.exit(1)
    if not run(dry_run=args.dry_run):
        sys.exit(1)


if __name__ == "__main__":
    main()
