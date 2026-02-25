"""Carga y validación de variables de entorno."""

import logging
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
LOG_DIR = BASE_DIR / "logs"
TEMPLATES_DIR = BASE_DIR / "templates"
TOPICS_FILE = BASE_DIR / "topics.yml"

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
    if WP_IMAGE_WIDTH <= 0 or WP_IMAGE_HEIGHT <= 0:
        logging.critical("WP_IMAGE_WIDTH y WP_IMAGE_HEIGHT deben ser mayores a 0")
        sys.exit(1)
    if WP_IMAGE_QUALITY <= 0 or WP_IMAGE_QUALITY > 100:
        logging.critical("WP_IMAGE_QUALITY debe estar entre 1 y 100")
        sys.exit(1)
    if MIN_BODY_WORDS < 300:
        logging.critical("MIN_BODY_WORDS debe ser al menos 300")
        sys.exit(1)
    if SOURCE_FETCH_MAX_CHARS < 2000:
        logging.critical("SOURCE_FETCH_MAX_CHARS debe ser al menos 2000")
        sys.exit(1)
    if LINK_CHECK_TIMEOUT <= 0:
        logging.critical("LINK_CHECK_TIMEOUT debe ser mayor a 0")
        sys.exit(1)
    if RECENT_POSTS_GALLERY_COUNT < 0:
        logging.critical("RECENT_POSTS_GALLERY_COUNT no puede ser negativo")
        sys.exit(1)
    if PREFERRED_EXTERNAL_LINK_EVERY < 0:
        logging.critical("PREFERRED_EXTERNAL_LINK_EVERY no puede ser negativo")
        sys.exit(1)
    for external_url in PREFERRED_EXTERNAL_LINKS:
        parsed = urlparse(external_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            logging.critical(
                "PREFERRED_EXTERNAL_LINKS contiene URL inválida: %s",
                external_url,
            )
            sys.exit(1)
    if TOPICS_MAX_POSTS_PER_RUN <= 0:
        logging.critical("TOPICS_MAX_POSTS_PER_RUN debe ser mayor a 0")
        sys.exit(1)
    if PUBLISH_INTERVAL_DAYS < 0:
        logging.critical("PUBLISH_INTERVAL_DAYS no puede ser negativo")
        sys.exit(1)
    if TRUSEO_MIN_SCORE < 0 or TRUSEO_MIN_SCORE > 100:
        logging.critical("TRUSEO_MIN_SCORE debe estar entre 0 y 100")
        sys.exit(1)
    if HEADLINE_MIN_SCORE < 0 or HEADLINE_MIN_SCORE > 100:
        logging.critical("HEADLINE_MIN_SCORE debe estar entre 0 y 100")
        sys.exit(1)
    if POST_TITLE_MAX_LEN < 40 or POST_TITLE_MAX_LEN > 120:
        logging.critical("POST_TITLE_MAX_LEN debe estar entre 40 y 120")
        sys.exit(1)
    if SOCIAL_TITLE_MAX_LEN < 40 or SOCIAL_TITLE_MAX_LEN > 120:
        logging.critical("SOCIAL_TITLE_MAX_LEN debe estar entre 40 y 120")
        sys.exit(1)
    if SOCIAL_DESCRIPTION_MAX_LEN < 120 or SOCIAL_DESCRIPTION_MAX_LEN > 200:
        logging.critical("SOCIAL_DESCRIPTION_MAX_LEN debe estar entre 120 y 200")
        sys.exit(1)
    if FOCUS_KEYPHRASE_MAX_WORDS < 2 or FOCUS_KEYPHRASE_MAX_WORDS > 8:
        logging.critical("FOCUS_KEYPHRASE_MAX_WORDS debe estar entre 2 y 8")
        sys.exit(1)
    if not SITE_TITLE:
        logging.critical("SITE_TITLE no puede estar vacío")
        sys.exit(1)
    if not TITLE_SEPARATOR.strip():
        logging.critical("TITLE_SEPARATOR no puede estar vacío")
        sys.exit(1)


GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SEARCH_PROVIDER = os.environ.get("SEARCH_PROVIDER", "brave").strip().lower()
BRAVE_SEARCH_API_KEY = os.environ.get("BRAVE_SEARCH_API_KEY", "")
BRAVE_SEARCH_COUNT = int(os.environ.get("BRAVE_SEARCH_COUNT", "20"))
BRAVE_SEARCH_COUNTRY = os.environ.get("BRAVE_SEARCH_COUNTRY", "").strip()
BRAVE_SEARCH_LANG = os.environ.get("BRAVE_SEARCH_LANG", "").strip()
BRAVE_SEARCH_FRESHNESS = os.environ.get("BRAVE_SEARCH_FRESHNESS", "pw").strip()
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
    for d in os.environ.get(
        "EXCLUDED_DOMAINS",
        "montessorimexico.org,montessori-ami.org,amiusa.org",
    ).split(",")
    if d.strip()
]
BLOCKED_SOURCE_TERMS = [
    t.strip().lower()
    for t in os.environ.get(
        "BLOCKED_SOURCE_TERMS",
        (
            "ami,amimontessori,misdami,ami_montessori,"
            "association montessori internationale,"
            "asociacion montessori internacional,"
            "ami/usa,ami usa,ami-eaa,ami mexico,"
            "asociacion montessori de mexico"
        ),
    ).split(",")
    if t.strip()
]
BLOCKED_MENTION_TERMS = [
    t.strip().lower()
    for t in os.environ.get(
        "BLOCKED_MENTION_TERMS",
        (
            "ami,amimontessori,misdami,ami_montessori,"
            "association montessori internationale,"
            "asociacion montessori internacional,"
            "ami/usa,ami usa,ami-eaa,ami mexico,"
            "asociacion montessori de mexico"
        ),
    ).split(",")
    if t.strip()
]

MIN_USABILITY_SCORE = float(os.environ.get("MIN_USABILITY_SCORE", "0.6"))
MIN_BODY_WORDS = int(os.environ.get("MIN_BODY_WORDS", "600"))
DRY_RUN = os.environ.get("DRY_RUN", "0") == "1"
GEMINI_TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
AIOSEO_SYNC = os.environ.get("AIOSEO_SYNC", "0") == "1"
LOCAL_SEO_RULES_ENABLED = os.environ.get("LOCAL_SEO_RULES_ENABLED", "1") == "1"
TRUSEO_MIN_SCORE = int(os.environ.get("TRUSEO_MIN_SCORE", "70"))
HEADLINE_MIN_SCORE = int(os.environ.get("HEADLINE_MIN_SCORE", "65"))
SEO_STRICT_PHRASE = os.environ.get("SEO_STRICT_PHRASE", "1") == "1"
NOTIFICATIONS_ENABLED = os.environ.get("NOTIFICATIONS_ENABLED", "1") == "1"
NOTIFY_WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
POST_TITLE_MAX_LEN = int(os.environ.get("POST_TITLE_MAX_LEN", "60"))
SEO_TITLE_MAX_LEN = int(os.environ.get("SEO_TITLE_MAX_LEN", "60"))
SEO_DESCRIPTION_MAX_LEN = int(os.environ.get("SEO_DESCRIPTION_MAX_LEN", "155"))
SOCIAL_TITLE_MAX_LEN = int(os.environ.get("SOCIAL_TITLE_MAX_LEN", "60"))
SOCIAL_DESCRIPTION_MAX_LEN = int(os.environ.get("SOCIAL_DESCRIPTION_MAX_LEN", "155"))
FOCUS_KEYPHRASE_MAX_WORDS = int(os.environ.get("FOCUS_KEYPHRASE_MAX_WORDS", "5"))
EXCERPT_MAX_LEN = int(os.environ.get("EXCERPT_MAX_LEN", "160"))
MAX_TAGS = int(os.environ.get("MAX_TAGS", "10"))
SITE_TITLE = os.environ.get("SITE_TITLE", "Asociación Montessori de México").strip()
TITLE_SEPARATOR = os.environ.get("TITLE_SEPARATOR", "|").strip()
WP_IMAGE_WIDTH = int(os.environ.get("WP_IMAGE_WIDTH", "1200"))
WP_IMAGE_HEIGHT = int(os.environ.get("WP_IMAGE_HEIGHT", "630"))
WP_IMAGE_QUALITY = int(os.environ.get("WP_IMAGE_QUALITY", "90"))
WP_IMAGE_MAX_KB = int(os.environ.get("WP_IMAGE_MAX_KB", "450"))
SOURCE_FETCH_ENABLED = os.environ.get("SOURCE_FETCH_ENABLED", "1") == "1"
SOURCE_FETCH_MAX_CHARS = int(os.environ.get("SOURCE_FETCH_MAX_CHARS", "15000"))
LINK_VALIDATION_ENABLED = os.environ.get("LINK_VALIDATION_ENABLED", "1") == "1"
LINK_CHECK_TIMEOUT = int(os.environ.get("LINK_CHECK_TIMEOUT", "8"))
RECENT_POSTS_GALLERY_COUNT = int(os.environ.get("RECENT_POSTS_GALLERY_COUNT", "4"))
PREFERRED_EXTERNAL_LINK_EVERY = int(os.environ.get("PREFERRED_EXTERNAL_LINK_EVERY", "3"))
PREFERRED_EXTERNAL_LINKS = [
    u.strip()
    for u in os.environ.get(
        "PREFERRED_EXTERNAL_LINKS",
        (
            "https://certificacionmontessori.com,"
            "https://asociacionmontessori.com.mx,"
            "https://kalpilli.com"
        ),
    ).split(",")
    if u.strip()
]
TOPIC_IDS = [
    t.strip()
    for t in os.environ.get("TOPIC_IDS", "").split(",")
    if t.strip()
]
TOPICS_MAX_POSTS_PER_RUN = int(os.environ.get("TOPICS_MAX_POSTS_PER_RUN", "1"))
PUBLISH_INTERVAL_DAYS = int(os.environ.get("PUBLISH_INTERVAL_DAYS", "7"))
DB_PATH = DATA_DIR / "blog_state.db"
WP_SITE_DOMAIN = (urlparse(WP_SITE_URL).netloc or "").lower()
INTERNAL_LINKS = [
    u.strip()
    for u in os.environ.get(
        "INTERNAL_LINKS",
        f"{WP_SITE_URL}/,{WP_SITE_URL}/blog/",
    ).split(",")
    if u.strip()
]


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
