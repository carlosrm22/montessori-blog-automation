"""Redact credentials from every rendered log record."""

from __future__ import annotations

import logging
import re


_TELEGRAM_URL = re.compile(r"(https://api\.telegram\.org/bot)[^/\s]+", re.I)
_NAMED_SECRET = re.compile(
    r"(?i)\b(TELEGRAM_BOT_TOKEN|WP_APP_PASSWORD|GEMINI_API_KEY|"
    r"BRAVE_SEARCH_API_KEY|GOOGLE_CSE_KEY)\s*[:=]\s*[^\r\n]+"
)


def redact_text(value: object) -> str:
    text = str(value)
    text = _TELEGRAM_URL.sub(r"\1[REDACTED]", text)
    return _NAMED_SECRET.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))
