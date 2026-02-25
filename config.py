"""Carga y validación de variables de entorno."""

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
LOG_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "templates"

load_dotenv(BASE_DIR / ".env")

REQUIRED_VARS = [
    "GEMINI_API_KEY",
    "GOOGLE_CSE_KEY",
    "GOOGLE_CSE_CX",
    "WP_SITE_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
]


def _get_required(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        logging.critical("Variable de entorno requerida no definida: %s", name)
        sys.exit(1)
    return val


def validate() -> None:
    """Valida que todas las variables requeridas estén definidas."""
    for var in REQUIRED_VARS:
        _get_required(var)


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")
WP_SITE_URL = os.environ.get("WP_SITE_URL", "").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")

SEARCH_QUERIES = [
    q.strip()
    for q in os.environ.get(
        "SEARCH_QUERIES",
        "noticias Montessori Mexico,educación Montessori México 2026,método Montessori novedades",
    ).split(",")
    if q.strip()
]

MIN_USABILITY_SCORE = float(os.environ.get("MIN_USABILITY_SCORE", "0.6"))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
DB_PATH = DATA_DIR / "blog_state.db"


def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    from logging.handlers import RotatingFileHandler

    handler = RotatingFileHandler(
        LOG_DIR / "automation.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[handler, logging.StreamHandler()],
    )


if __name__ == "__main__":
    setup_logging()
    validate()
    logging.info("Configuración válida. DRY_RUN=%s", DRY_RUN)
