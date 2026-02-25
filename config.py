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

BASE_REQUIRED_VARS = [
    "GEMINI_API_KEY",
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
    for var in BASE_REQUIRED_VARS:
        _get_required(var)
    if SEARCH_PROVIDER == "brave":
        _get_required("BRAVE_SEARCH_API_KEY")
    elif SEARCH_PROVIDER == "google_cse":
        _get_required("GOOGLE_CSE_KEY")
        _get_required("GOOGLE_CSE_CX")
    else:
        logging.critical(
            "SEARCH_PROVIDER inválido: %s. Valores válidos: brave, google_cse",
            SEARCH_PROVIDER,
        )
        sys.exit(1)
    if BRAVE_SEARCH_COUNT <= 0:
        logging.critical("BRAVE_SEARCH_COUNT debe ser mayor a 0")
        sys.exit(1)


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SEARCH_PROVIDER = os.environ.get("SEARCH_PROVIDER", "brave").strip().lower()
BRAVE_SEARCH_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_COUNT = int(os.environ.get("BRAVE_SEARCH_COUNT", "20"))
BRAVE_SEARCH_COUNTRY = os.environ.get("BRAVE_SEARCH_COUNTRY", "").strip()
BRAVE_SEARCH_LANG = os.environ.get("BRAVE_SEARCH_LANG", "").strip()
GOOGLE_CSE_KEY = os.environ.get("GOOGLE_CSE_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")
WP_SITE_URL = os.environ.get("WP_SITE_URL", "").rstrip("/")
WP_USERNAME = os.environ.get("WP_USERNAME", "")
WP_APP_PASSWORD = os.environ.get("WP_APP_PASSWORD", "")

SEARCH_QUERIES = [
    q.strip()
    for q in os.environ.get(
        "SEARCH_QUERIES",
        "Montessori,Montessori education,Montessori method,método Montessori,méthode Montessori,Montessori news",
    ).split(",")
    if q.strip()
]
EXCLUDED_DOMAINS = [
    d.strip().lower()
    for d in os.environ.get("EXCLUDED_DOMAINS", "montessorimexico.org").split(",")
    if d.strip()
]

MIN_USABILITY_SCORE = float(os.environ.get("MIN_USABILITY_SCORE", "0.6"))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
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
