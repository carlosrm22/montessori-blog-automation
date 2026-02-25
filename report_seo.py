"""CLI to inspect stored local SEO reports from SQLite."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime

import config


def _format_dt(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "-"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.isoformat(timespec="seconds")
    except Exception:
        return raw


def _load_rows(limit: int, topic_id: str | None, only_failed: bool) -> list[sqlite3.Row]:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT
            sr.topic_id,
            sr.url,
            sr.truseo_score,
            sr.headline_score,
            sr.created_at,
            pa.status,
            pa.title
        FROM seo_reports sr
        LEFT JOIN processed_articles pa
            ON pa.topic_id = sr.topic_id AND pa.url = sr.url
    """
    params: list[object] = []
    where: list[str] = []
    if topic_id:
        where.append("sr.topic_id = ?")
        params.append(topic_id)
    if only_failed:
        where.append("pa.status = 'seo_failed'")
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY sr.created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Show local TruSEO/headline reports")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to display")
    parser.add_argument("--topic-id", default="", help="Filter by topic_id")
    parser.add_argument(
        "--only-failed",
        action="store_true",
        help="Show only rows marked as seo_failed in processed_articles",
    )
    parser.add_argument("--json", action="store_true", help="Print as JSON")
    args = parser.parse_args()

    rows = _load_rows(
        limit=max(args.limit, 1),
        topic_id=args.topic_id.strip() or None,
        only_failed=args.only_failed,
    )

    if args.json:
        payload = [dict(row) for row in rows]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not rows:
        print("No hay reportes SEO para los filtros indicados.")
        return

    print(
        "created_at | topic_id | status | truseo | headline | title/url"
    )
    print("-" * 120)
    for row in rows:
        title = (row["title"] or "").strip() or row["url"]
        line = (
            f"{_format_dt(str(row['created_at']))} | "
            f"{row['topic_id']} | "
            f"{(row['status'] or '-')} | "
            f"{row['truseo_score']} | "
            f"{row['headline_score']} | "
            f"{title}"
        )
        print(line)


if __name__ == "__main__":
    main()

