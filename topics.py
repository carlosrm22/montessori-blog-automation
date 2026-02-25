"""Topic profile loading and validation."""

from dataclasses import dataclass
from pathlib import Path

import yaml

import config


@dataclass
class TopicProfile:
    topic_id: str
    name: str
    author_name: str
    brand_kit: str
    queries: list[str]
    categories: list[str]
    min_score: float
    post_template: str
    scoring_guidelines: str
    writing_guidelines: str


def _normalize_topic(raw: dict) -> TopicProfile:
    topic_id = str(raw.get("id", "")).strip()
    if not topic_id:
        raise ValueError("Topic missing 'id'")
    name = str(raw.get("name", topic_id)).strip()
    author_name = str(raw.get("author_name", "")).strip()
    brand_kit = str(raw.get("brand_kit", config.BRAND_KIT)).strip().lower() or config.BRAND_KIT
    queries = [str(q).strip() for q in raw.get("queries", []) if str(q).strip()]
    if not queries:
        raise ValueError(f"Topic '{topic_id}' has no queries")
    categories = [str(c).strip() for c in raw.get("categories", []) if str(c).strip()]
    min_score = float(raw.get("min_score", config.MIN_USABILITY_SCORE))
    post_template = str(raw.get("post_template", "post_prompt.txt")).strip() or "post_prompt.txt"
    scoring_guidelines = str(raw.get("scoring_guidelines", "")).strip()
    writing_guidelines = str(raw.get("writing_guidelines", "")).strip()
    return TopicProfile(
        topic_id=topic_id,
        name=name,
        author_name=author_name,
        brand_kit=brand_kit,
        queries=queries,
        categories=categories,
        min_score=min_score,
        post_template=post_template,
        scoring_guidelines=scoring_guidelines,
        writing_guidelines=writing_guidelines,
    )


def _default_topic() -> TopicProfile:
    return TopicProfile(
        topic_id="montessori_core",
        name="Montessori Global",
        author_name="",
        brand_kit=config.BRAND_KIT,
        queries=config.SEARCH_QUERIES,
        categories=["Educación Montessori"],
        min_score=config.MIN_USABILITY_SCORE,
        post_template="post_prompt.txt",
        scoring_guidelines="Prioriza noticia verificable y aplicabilidad educativa en contexto internacional.",
        writing_guidelines="Mantén enfoque práctico para familias y educadores de distintos países.",
    )


def load_topics(path: Path | None = None, only_ids: list[str] | None = None) -> list[TopicProfile]:
    path = path or config.TOPICS_FILE
    if not path.exists():
        return [_default_topic()]

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_topics = data.get("topics", [])
    if not isinstance(raw_topics, list) or not raw_topics:
        return [_default_topic()]

    topics = [_normalize_topic(raw) for raw in raw_topics]
    seen: set[str] = set()
    for topic in topics:
        if topic.topic_id in seen:
            raise ValueError(f"Duplicate topic id: {topic.topic_id}")
        seen.add(topic.topic_id)

    if only_ids:
        allowed = {i.strip() for i in only_ids if i.strip()}
        topics = [t for t in topics if t.topic_id in allowed]
    return topics or [_default_topic()]
