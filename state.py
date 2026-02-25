"""SQLite state management to avoid processing duplicates."""

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS processed_articles (
    url TEXT PRIMARY KEY,
    title TEXT,
    score REAL,
    wp_post_id INTEGER,
    status TEXT DEFAULT 'processed',
    created_at TEXT DEFAULT (datetime('now'))
)
"""


def _connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def is_processed(url: str) -> bool:
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM processed_articles WHERE url = ?", (url,)
        ).fetchone()
        return row is not None


def mark_processed(
    url: str,
    title: str = "",
    score: float = 0.0,
    wp_post_id: int | None = None,
    status: str = "processed",
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO processed_articles
               (url, title, score, wp_post_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (url, title, score, wp_post_id, status, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    logger.info("Marcado como procesado: %s (score=%.2f, wp_id=%s)", url, score, wp_post_id)


def get_all_processed_urls() -> set[str]:
    with _connect() as conn:
        rows = conn.execute("SELECT url FROM processed_articles").fetchall()
        return {row[0] for row in rows}


if __name__ == "__main__":
    config.setup_logging()
    mark_processed("https://example.com/test", title="Test", score=0.8)
    print("Is processed:", is_processed("https://example.com/test"))
    print("All URLs:", get_all_processed_urls())
    # Cleanup test
    with _connect() as conn:
        conn.execute("DELETE FROM processed_articles WHERE url = 'https://example.com/test'")
        conn.commit()
    print("Cleanup done.")
