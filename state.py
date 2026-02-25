"""SQLite state management by topic to avoid processing duplicates."""

import sqlite3
import logging
from datetime import datetime, timezone
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS processed_articles (
    topic_id TEXT NOT NULL DEFAULT 'default',
    url TEXT NOT NULL,
    title TEXT,
    score REAL,
    wp_post_id INTEGER,
    status TEXT DEFAULT 'processed',
    created_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (topic_id, url)
)
"""


def _connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def _migrate_if_needed(conn: sqlite3.Connection) -> None:
    """Migrate old single-key table to topic-aware schema if needed."""
    cols = {
        row[1] for row in conn.execute("PRAGMA table_info(processed_articles)").fetchall()
    }
    if "topic_id" in cols:
        return
    rows = conn.execute(
        "SELECT url, title, score, wp_post_id, status, created_at FROM processed_articles"
    ).fetchall()
    conn.execute("ALTER TABLE processed_articles RENAME TO processed_articles_old")
    conn.execute(_CREATE_TABLE)
    conn.executemany(
        """INSERT OR REPLACE INTO processed_articles
           (topic_id, url, title, score, wp_post_id, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [("default", *row) for row in rows],
    )
    conn.execute("DROP TABLE processed_articles_old")
    conn.commit()


def is_processed(url: str, topic_id: str = "default") -> bool:
    with _connect() as conn:
        _migrate_if_needed(conn)
        row = conn.execute(
            "SELECT 1 FROM processed_articles WHERE topic_id = ? AND url = ?",
            (topic_id, url),
        ).fetchone()
        return row is not None


def mark_processed(
    url: str,
    title: str = "",
    score: float = 0.0,
    wp_post_id: int | None = None,
    status: str = "processed",
    topic_id: str = "default",
) -> None:
    with _connect() as conn:
        _migrate_if_needed(conn)
        conn.execute(
            """INSERT OR REPLACE INTO processed_articles
               (topic_id, url, title, score, wp_post_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                topic_id, url, title, score, wp_post_id, status,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    logger.info(
        "Marcado como procesado [%s]: %s (score=%.2f, wp_id=%s)",
        topic_id, url, score, wp_post_id,
    )


def get_all_processed_urls(topic_id: str = "default") -> set[str]:
    with _connect() as conn:
        _migrate_if_needed(conn)
        rows = conn.execute(
            "SELECT url FROM processed_articles WHERE topic_id = ?",
            (topic_id,),
        ).fetchall()
        return {row[0] for row in rows}


def _parse_created_at(value: str) -> datetime | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_last_published_at(
    statuses: tuple[str, ...] = ("published_draft",),
    topic_id: str | None = None,
) -> datetime | None:
    if not statuses:
        return None
    placeholders = ",".join("?" for _ in statuses)
    sql = (
        "SELECT created_at FROM processed_articles "
        f"WHERE status IN ({placeholders})"
    )
    params: list[str] = list(statuses)
    if topic_id:
        sql += " AND topic_id = ?"
        params.append(topic_id)
    sql += " ORDER BY created_at DESC LIMIT 1"

    with _connect() as conn:
        _migrate_if_needed(conn)
        row = conn.execute(sql, params).fetchone()
    if not row:
        return None
    return _parse_created_at(str(row[0]))


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
