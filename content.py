"""Genera artículo original optimizado para SEO usando Gemini."""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass

from google import genai
from jinja2 import Environment, FileSystemLoader

import config
from search import SearchResult

logger = logging.getLogger(__name__)
POST_SCHEMA = {
    "type": "object",
    "required": [
        "title", "body", "excerpt", "categories", "tags",
        "seo_title", "seo_description", "focus_keyphrase",
        "image_prompt", "image_alt_text",
    ],
    "properties": {
        "title": {"type": "string"},
        "body": {"type": "string"},
        "excerpt": {"type": "string"},
        "categories": {"type": "array", "items": {"type": "string"}},
        "tags": {"type": "array", "items": {"type": "string"}},
        "seo_title": {"type": "string"},
        "seo_description": {"type": "string"},
        "focus_keyphrase": {"type": "string"},
        "image_prompt": {"type": "string"},
        "image_alt_text": {"type": "string"},
    },
}


@dataclass
class GeneratedPost:
    title: str
    body: str
    excerpt: str
    categories: list[str]
    tags: list[str]
    seo_title: str
    seo_description: str
    focus_keyphrase: str
    image_prompt: str
    image_alt_text: str


def _render_prompt(
    article: SearchResult,
    topic_name: str = "Montessori",
    topic_writing_guidelines: str = "",
    template_name: str = "post_prompt.txt",
) -> str:
    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR))
    template = env.get_template(template_name)
    blocked_terms = ", ".join(config.BLOCKED_MENTION_TERMS)
    return template.render(
        topic_name=topic_name,
        topic_writing_guidelines=topic_writing_guidelines,
        title=article.title,
        url=article.url,
        snippet=article.snippet,
        source_text=article.source_text,
        source_published_at=article.source_published_at,
        source_author=article.source_author,
        blocked_terms=blocked_terms,
    )


def _count_words_html(html: str) -> int:
    """Rough word count stripping HTML tags."""
    from bs4 import BeautifulSoup
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return len(text.split())


def _html_to_text(html: str) -> str:
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser").get_text(separator=" ")


def _clean_spaces(text: str) -> str:
    return " ".join((text or "").split())


def _truncate(text: str, max_len: int, add_ellipsis: bool = False) -> str:
    text = _clean_spaces(text)
    if len(text) <= max_len:
        return text
    cut = text[:max_len].rsplit(" ", 1)[0] or text[:max_len]
    if add_ellipsis and len(cut) + 3 <= max_len:
        return f"{cut}..."
    return cut


def _normalize_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = _clean_spaces(str(raw))
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(tag)
        if len(normalized) >= config.MAX_TAGS:
            break
    return normalized


def _normalize_for_compare(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return " ".join(text.split())


def _contains_keyphrase(title: str, keyphrase: str) -> bool:
    title_n = _normalize_for_compare(title)
    phrase_n = _normalize_for_compare(keyphrase)
    if not phrase_n:
        return True
    if phrase_n in title_n:
        return True
    phrase_tokens = set(phrase_n.split())
    title_tokens = set(title_n.split())
    return bool(phrase_tokens) and phrase_tokens.issubset(title_tokens)


def _find_blocked_term(text: str) -> str | None:
    haystack = _normalize_for_compare(text)
    tokens = set(haystack.split())
    for term in config.BLOCKED_MENTION_TERMS:
        needle = _normalize_for_compare(term)
        if not needle:
            continue
        if len(needle) <= 3 and " " not in needle:
            if needle in tokens:
                return term
            continue
        if needle in haystack:
            return term
    return None


def _contains_blocked_mentions(post: GeneratedPost) -> str | None:
    candidates = [
        post.title,
        post.body,
        post.excerpt,
        post.seo_title,
        post.seo_description,
        post.focus_keyphrase,
        post.image_alt_text,
        " ".join(post.tags),
    ]
    for text in candidates:
        blocked = _find_blocked_term(text)
        if blocked:
            return blocked
    return None


def _extract_focus_keyphrase(data: dict, title: str, tags: list[str]) -> str:
    explicit = _clean_spaces(str(data.get("focus_keyphrase", "")))
    if explicit:
        return _truncate(explicit, 60)
    if tags:
        return _truncate(tags[0], 60)
    words = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9]+", title)
    phrase = " ".join(words[:4]) if words else "Montessori México"
    return _truncate(phrase, 60)


def _normalize_generated_post(data: dict) -> GeneratedPost:
    title = _truncate(
        data.get("title", "Actualidad Montessori en México"), 70
    )
    body = data.get("body", "")
    plain_text = _html_to_text(body)

    excerpt = _truncate(
        data.get("excerpt", "") or plain_text,
        config.EXCERPT_MAX_LEN,
        add_ellipsis=True,
    )
    categories = [
        _clean_spaces(str(c)) for c in data.get("categories", ["Educación Montessori"])
        if _clean_spaces(str(c))
    ] or ["Educación Montessori"]
    tags = _normalize_tags(data.get("tags", []))

    focus_keyphrase = _extract_focus_keyphrase(data, title, tags)

    seo_title = _truncate(data.get("seo_title", "") or title, config.SEO_TITLE_MAX_LEN)
    if not _contains_keyphrase(seo_title, focus_keyphrase):
        base_title = seo_title.rstrip(":,;.- ")
        seo_title = _truncate(
            f"{focus_keyphrase}: {base_title}",
            config.SEO_TITLE_MAX_LEN,
        )
    seo_description = _truncate(
        data.get("seo_description", "") or excerpt or plain_text,
        config.SEO_DESCRIPTION_MAX_LEN,
        add_ellipsis=True,
    )

    image_alt_text = _truncate(
        data.get("image_alt_text", "") or f"{title} - imagen de portada Montessori",
        125,
    )

    return GeneratedPost(
        title=title,
        body=body,
        excerpt=excerpt,
        categories=categories,
        tags=tags,
        seo_title=seo_title,
        seo_description=seo_description,
        focus_keyphrase=focus_keyphrase,
        image_prompt=_clean_spaces(data.get("image_prompt", "")),
        image_alt_text=image_alt_text,
    )


def generate_post(
    article: SearchResult,
    max_retries: int = 2,
    topic_name: str = "Montessori",
    topic_writing_guidelines: str = "",
    template_name: str = "post_prompt.txt",
) -> GeneratedPost | None:
    """Generate an original blog post from a source article."""
    prompt = _render_prompt(
        article,
        topic_name=topic_name,
        topic_writing_guidelines=topic_writing_guidelines,
        template_name=template_name,
    )
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=config.GEMINI_TEXT_MODEL,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=POST_SCHEMA,
                ),
            )
            text = (response.text or "").strip()
            try:
                data = json.loads(text)
            except Exception:
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    if text.endswith("```"):
                        text = text[:-3]
                    text = text.strip()
                data = json.loads(text)
            body = data.get("body", "")
            word_count = _count_words_html(body)

            if word_count < config.MIN_BODY_WORDS:
                logger.warning(
                    "Attempt %d: body too short (%d words < %d), retrying/aborting",
                    attempt + 1, word_count, config.MIN_BODY_WORDS,
                )
                if attempt < max_retries - 1:
                    continue
                return None

            post = _normalize_generated_post(data)
            blocked = _contains_blocked_mentions(post)
            if blocked:
                logger.warning(
                    "Attempt %d: post contains blocked term '%s', retrying/aborting",
                    attempt + 1, blocked,
                )
                if attempt < max_retries - 1:
                    continue
                return None
            logger.info(
                "Artículo generado: '%s' (%d palabras)", post.title, word_count
            )
            return post

        except Exception as exc:
            logger.warning("Content generation attempt %d failed: %s", attempt + 1, exc)
            if attempt < max_retries - 1:
                continue

    logger.error("Failed to generate content after %d attempts", max_retries)
    return None


if __name__ == "__main__":
    config.setup_logging()
    config.validate()
    test = SearchResult(
        title="Nueva escuela Montessori abre en CDMX",
        url="https://example.com/noticia",
        snippet="Una nueva escuela con método Montessori abrirá sus puertas en la Ciudad de México para el ciclo 2026.",
    )
    post = generate_post(test)
    if post:
        print(f"Title: {post.title}")
        print(f"Excerpt: {post.excerpt}")
        print(f"Tags: {post.tags}")
        print(f"Image prompt: {post.image_prompt}")
        print(f"Body preview: {post.body[:300]}...")
