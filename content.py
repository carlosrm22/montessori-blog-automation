"""Genera artículo original optimizado para SEO usando Gemini."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import urlparse

from google import genai
from jinja2 import Environment, FileSystemLoader

import config
from search import SearchResult

logger = logging.getLogger(__name__)
POST_SCHEMA = {
    "type": "object",
    "required": [
        "title",
        "body",
        "excerpt",
        "categories",
        "tags",
        "seo_title",
        "seo_description",
        "focus_keyphrase",
        "image_prompt",
        "image_alt_text",
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
        "og_title": {"type": "string"},
        "og_description": {"type": "string"},
        "twitter_title": {"type": "string"},
        "twitter_description": {"type": "string"},
        "social_image_source": {"type": "string"},
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
    og_title: str
    og_description: str
    twitter_title: str
    twitter_description: str
    social_image_source: str
    image_prompt: str
    image_alt_text: str


def _is_public_source_url(url: str) -> bool:
    try:
        parsed = urlparse((url or "").strip())
    except Exception:
        return False
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in ("http", "https"):
        return False
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
        return False
    if host.endswith(".local"):
        return False
    return True


def _load_author_tone(tone_file: str) -> str:
    """Carga la guía de tono/voz de un autor desde tones/. Tolerante a faltantes."""
    name = (tone_file or "").strip()
    if not name:
        return ""
    path = (config.TONES_DIR / name).resolve()
    # Evita escapes fuera de la carpeta de tonos.
    if config.TONES_DIR.resolve() not in path.parents:
        logger.warning("tone_file '%s' fuera de TONES_DIR; se ignora.", tone_file)
        return ""
    if not path.is_file():
        logger.warning("Tono de autor no encontrado: %s (se generará sin voz específica).", path)
        return ""
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        logger.warning("No se pudo leer el tono '%s': %s", path, exc)
        return ""


def _render_prompt(
    article: SearchResult,
    topic_name: str = "Montessori",
    topic_writing_guidelines: str = "",
    template_name: str = "post_prompt.txt",
    author_name: str = "",
    author_tone: str = "",
) -> str:
    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR))
    template = env.get_template(template_name)
    blocked_terms = ", ".join(config.BLOCKED_MENTION_TERMS)
    source_public_url = _is_public_source_url(article.url)
    return template.render(
        topic_name=topic_name,
        topic_writing_guidelines=topic_writing_guidelines,
        author_name=author_name,
        author_tone=author_tone,
        site_title=config.SITE_TITLE,
        title_separator=config.TITLE_SEPARATOR,
        title=article.title,
        url=article.url,
        source_public_url=source_public_url,
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


def _contains_exact_phrase(text: str, phrase: str) -> bool:
    haystack = _clean_spaces(text)
    needle = _clean_spaces(phrase)
    if not haystack or not needle:
        return False
    pattern = r"(?<!\w)" + re.escape(needle) + r"(?!\w)"
    return re.search(pattern, haystack, flags=re.IGNORECASE | re.UNICODE) is not None


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


def _derive_focus_phrase_candidate(text: str, max_words: int = 5) -> str:
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü0-9]+", _clean_spaces(text))
    if not tokens:
        return ""
    trimmed = tokens[:max_words]
    trailing_stopwords = {
        "a", "al", "con", "de", "del", "e", "el", "en", "la", "las",
        "los", "para", "por", "un", "una", "y",
    }
    while len(trimmed) > 2 and trimmed[-1].lower() in trailing_stopwords:
        trimmed.pop()
    return _truncate(" ".join(trimmed), 60)


def _normalize_for_compare(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())
    return " ".join(text.split())


def _contains_keyphrase(text: str, keyphrase: str) -> bool:
    text_n = _normalize_for_compare(text)
    phrase_n = _normalize_for_compare(keyphrase)
    if not phrase_n:
        return True
    if phrase_n in text_n:
        return True
    phrase_tokens = set(phrase_n.split())
    text_tokens = set(text_n.split())
    return bool(phrase_tokens) and phrase_tokens.issubset(text_tokens)


def _ensure_keyphrase(text: str, keyphrase: str, max_len: int) -> str:
    text = _truncate(text, max_len, add_ellipsis=True)
    if not keyphrase:
        return text
    if _contains_keyphrase(text, keyphrase):
        return text
    return _truncate(f"{keyphrase}: {text}", max_len, add_ellipsis=True)


def _with_site_suffix(title: str, max_len: int) -> str:
    base = _truncate(title, max_len)
    site_title = _clean_spaces(config.SITE_TITLE)
    separator = _clean_spaces(config.TITLE_SEPARATOR) or "|"
    if not site_title:
        return base
    base_norm = _normalize_for_compare(base)
    site_norm = _normalize_for_compare(site_title)
    if site_norm and site_norm in base_norm:
        return base

    suffix = f" {separator} {site_title}"
    if len(base) + len(suffix) <= max_len:
        return f"{base}{suffix}"

    allowed_base_len = max_len - len(suffix)
    if allowed_base_len <= 10:
        # If max_len is too short, keep a usable plain title.
        return _truncate(base, max_len)
    base_cut = _truncate(base, allowed_base_len).rstrip(" :;,-|/")
    return f"{base_cut}{suffix}"


def _strip_site_suffix(title: str) -> str:
    base = (title or "").strip()
    site_title = _clean_spaces(config.SITE_TITLE)
    separator = _clean_spaces(config.TITLE_SEPARATOR) or "|"
    if not base or not site_title:
        return base

    suffix = f" {separator} {site_title}"
    if base.endswith(suffix):
        return base[: -len(suffix)].rstrip(" :;,-|/")
    return base


def _max_base_len_with_site_suffix(max_len: int) -> int:
    site_title = _clean_spaces(config.SITE_TITLE)
    separator = _clean_spaces(config.TITLE_SEPARATOR) or "|"
    if not site_title:
        return max_len
    suffix_len = len(f" {separator} {site_title}")
    # Keep enough room for a meaningful base title.
    return max(15, max_len - suffix_len)


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


def _is_internal_href(href: str) -> bool:
    href = (href or "").strip()
    if not href or href.startswith(("#", "mailto:", "tel:")):
        return False
    if href.startswith("/"):
        return True
    parsed = urlparse(href)
    if not parsed.netloc:
        return True
    host = parsed.netloc.lower()
    site = config.WP_SITE_DOMAIN
    if not site:
        return False
    return host == site or host.endswith(f".{site}")


def _count_internal_links(html: str) -> int:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    count = 0
    for a in soup.find_all("a", href=True):
        if _is_internal_href(a.get("href", "")):
            count += 1
    return count


def _link_label(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "").strip("/")
    if not path:
        return "Inicio Montessori"
    parts = [p for p in path.split("/") if p][:4]
    if not parts:
        return "Recurso recomendado"
    label = " ".join(part.replace("-", " ") for part in parts)
    return label.title()[:80]


def _ensure_internal_links(body: str) -> str:
    if _count_internal_links(body) >= 1:
        return body
    links = [u for u in config.INTERNAL_LINKS if u]
    if not links:
        return body
    items = "\n".join(
        f'<li><a href="{link}">{_link_label(link)}</a></li>'
        for link in links[:3]
    )
    block = (
        "\n<h2>Recursos Internos Recomendados</h2>\n"
        "<ul>\n"
        f"{items}\n"
        "</ul>\n"
    )
    return (body or "").rstrip() + block


def _contains_blocked_mentions(post: GeneratedPost) -> str | None:
    candidates = [
        post.title,
        post.body,
        post.excerpt,
        _strip_site_suffix(post.seo_title),
        post.seo_description,
        post.focus_keyphrase,
        _strip_site_suffix(post.og_title),
        post.og_description,
        _strip_site_suffix(post.twitter_title),
        post.twitter_description,
        post.image_alt_text,
        " ".join(post.tags),
    ]
    for text in candidates:
        blocked = _find_blocked_term(text)
        if blocked:
            return blocked
    return None


def _extract_focus_keyphrase(data: dict, title: str, plain_text: str, tags: list[str]) -> str:
    explicit = _clean_spaces(str(data.get("focus_keyphrase", "")))
    title_prefix = re.split(r"[:|/\-]", title, maxsplit=1)[0]
    candidates = [
        explicit,
        _derive_focus_phrase_candidate(title_prefix),
        _derive_focus_phrase_candidate(title),
        _derive_focus_phrase_candidate(tags[0]) if tags else "",
    ]
    searchable_text = f"{title} {plain_text}"
    for candidate in candidates:
        if candidate and _contains_exact_phrase(searchable_text, candidate):
            return candidate
    for candidate in candidates:
        if candidate:
            return candidate
    return "Educación Montessori"


def _ensure_exact_phrase(text: str, phrase: str, max_len: int) -> str:
    base = _truncate(text, max_len, add_ellipsis=True)
    phrase = _clean_spaces(phrase)
    if not phrase:
        return base
    if _contains_exact_phrase(base, phrase):
        return base
    if not base:
        return _truncate(phrase, max_len)
    candidate = f"{phrase}: {base}"
    if len(candidate) <= max_len:
        return candidate
    remaining = max_len - len(phrase) - 2
    if remaining <= 0:
        return _truncate(phrase, max_len)
    return f"{phrase}: {_truncate(base, remaining, add_ellipsis=True)}"


def _body_has_keyphrase_in_subheading(body: str, keyphrase: str) -> bool:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body or "", "html.parser")
    for heading in soup.find_all(["h2", "h3"]):
        if _contains_exact_phrase(heading.get_text(" ", strip=True), keyphrase):
            return True
    return False


def _align_focus_keyphrase(post: GeneratedPost) -> GeneratedPost:
    if not post.focus_keyphrase:
        return post

    seo_base = _ensure_exact_phrase(
        _strip_site_suffix(post.seo_title),
        post.focus_keyphrase,
        _max_base_len_with_site_suffix(config.SEO_TITLE_MAX_LEN),
    )
    post.seo_title = _with_site_suffix(seo_base, config.SEO_TITLE_MAX_LEN)
    post.seo_description = _ensure_exact_phrase(
        post.seo_description,
        post.focus_keyphrase,
        config.SEO_DESCRIPTION_MAX_LEN,
    )
    post.og_description = _ensure_exact_phrase(
        post.og_description,
        post.focus_keyphrase,
        config.SOCIAL_DESCRIPTION_MAX_LEN,
    )
    post.twitter_description = _ensure_exact_phrase(
        post.twitter_description,
        post.focus_keyphrase,
        config.SOCIAL_DESCRIPTION_MAX_LEN,
    )

    body_text = _html_to_text(post.body)
    if not _contains_exact_phrase(body_text, post.focus_keyphrase):
        intro = (
            f"<p><strong>{post.focus_keyphrase}</strong> "
            "ofrece una lente clara para interpretar la fuente y convertirla "
            "en decisiones pedagógicas concretas.</p>\n"
        )
        post.body = intro + (post.body or "").lstrip()
    if not _body_has_keyphrase_in_subheading(post.body, post.focus_keyphrase):
        section = (
            f"\n<h2>{post.focus_keyphrase} en la práctica educativa</h2>\n"
            "<p>Este enfoque ayuda a traducir los hallazgos del artículo en "
            "acciones observables para aula, familia y comunidad escolar.</p>\n"
        )
        post.body = (post.body or "").rstrip() + section
    return post


def _normalize_generated_post(data: dict) -> GeneratedPost:
    title = _truncate(
        data.get("title", "Actualidad Montessori Internacional"),
        config.POST_TITLE_MAX_LEN,
    )

    body = data.get("body", "")
    plain_text = _html_to_text(body)

    excerpt = _truncate(
        data.get("excerpt", "") or plain_text,
        config.EXCERPT_MAX_LEN,
        add_ellipsis=True,
    )
    categories = [
        _clean_spaces(str(c))
        for c in data.get("categories", ["Educación Montessori"])
        if _clean_spaces(str(c))
    ] or ["Educación Montessori"]
    tags = _normalize_tags(data.get("tags", []))

    focus_keyphrase = _extract_focus_keyphrase(data, title, plain_text, tags)

    seo_base_max_len = _max_base_len_with_site_suffix(config.SEO_TITLE_MAX_LEN)
    seo_base = _truncate(data.get("seo_title", "") or title, seo_base_max_len)
    if not _contains_keyphrase(seo_base, focus_keyphrase):
        key_words = focus_keyphrase.split()
        seo_words = seo_base.split()
        if (
            key_words
            and seo_words
            and _normalize_for_compare(key_words[0]) == _normalize_for_compare(seo_words[0])
        ):
            merged = " ".join([focus_keyphrase, *seo_words[1:]])
        else:
            merged = f"{focus_keyphrase} {seo_base}"
        seo_base = _truncate(merged, seo_base_max_len)
    seo_title = seo_base
    seo_title = _with_site_suffix(seo_title, config.SEO_TITLE_MAX_LEN)

    seo_description = _truncate(
        data.get("seo_description", "") or excerpt or plain_text,
        config.SEO_DESCRIPTION_MAX_LEN,
        add_ellipsis=True,
    )
    seo_description = _ensure_keyphrase(seo_description, focus_keyphrase, config.SEO_DESCRIPTION_MAX_LEN)

    og_title = _truncate(
        data.get("og_title", "") or data.get("social_og_title", "") or seo_title,
        config.SOCIAL_TITLE_MAX_LEN,
    )
    og_title = _with_site_suffix(og_title, config.SOCIAL_TITLE_MAX_LEN)
    og_description = _truncate(
        data.get("og_description", "") or data.get("social_og_description", "") or seo_description,
        config.SOCIAL_DESCRIPTION_MAX_LEN,
        add_ellipsis=True,
    )
    og_description = _ensure_keyphrase(og_description, focus_keyphrase, config.SOCIAL_DESCRIPTION_MAX_LEN)

    twitter_title = _truncate(
        data.get("twitter_title", "") or data.get("social_twitter_title", "") or og_title,
        config.SOCIAL_TITLE_MAX_LEN,
    )
    twitter_title = _with_site_suffix(twitter_title, config.SOCIAL_TITLE_MAX_LEN)
    twitter_description = _truncate(
        data.get("twitter_description", "") or data.get("social_twitter_description", "") or og_description,
        config.SOCIAL_DESCRIPTION_MAX_LEN,
        add_ellipsis=True,
    )
    twitter_description = _ensure_keyphrase(
        twitter_description,
        focus_keyphrase,
        config.SOCIAL_DESCRIPTION_MAX_LEN,
    )

    social_image_source = "featured_media"

    image_alt_text = _truncate(
        data.get("image_alt_text", "") or f"{title} - imagen de portada Montessori",
        125,
    )

    post = GeneratedPost(
        title=title,
        body=body,
        excerpt=excerpt,
        categories=categories,
        tags=tags,
        seo_title=seo_title,
        seo_description=seo_description,
        focus_keyphrase=focus_keyphrase,
        og_title=og_title,
        og_description=og_description,
        twitter_title=twitter_title,
        twitter_description=twitter_description,
        social_image_source=social_image_source,
        image_prompt=_clean_spaces(data.get("image_prompt", "")),
        image_alt_text=image_alt_text,
    )
    return _align_focus_keyphrase(post)


def _build_retry_guidance(last_error: str | None) -> str:
    if not last_error:
        return ""
    if last_error.startswith("blocked:"):
        blocked_term = last_error.split(":", 1)[1]
        return (
            "\n\n## Correccion obligatoria del intento anterior\n"
            f"- El intento anterior incluyo el termino bloqueado '{blocked_term}'.\n"
            "- No incluyas ese termino ni variantes en body, excerpt, tags, keyphrase o metadata.\n"
            "- Devuelve titulos SEO/social limpios y sin sufijo de marca; el pipeline agregara la marca despues.\n"
        )
    if last_error.startswith("short:"):
        return (
            "\n\n## Correccion obligatoria del intento anterior\n"
            "- El intento anterior quedo demasiado corto.\n"
            "- Esta vez entrega entre 750 y 950 palabras reales en el body HTML.\n"
            "- Amplia contexto, implicaciones y recomendaciones practicas sin inventar datos.\n"
        )
    return ""


def generate_post(
    article: SearchResult,
    max_retries: int = 2,
    topic_name: str = "Montessori",
    topic_writing_guidelines: str = "",
    template_name: str = "post_prompt.txt",
    author_name: str = "",
    tone_file: str = "",
) -> GeneratedPost | None:
    """Generate an original blog post from a source article."""
    author_tone = _load_author_tone(tone_file)
    if author_tone:
        logger.info("Aplicando voz del autor '%s' (tono: %s)", author_name, tone_file)
    base_prompt = _render_prompt(
        article,
        topic_name=topic_name,
        topic_writing_guidelines=topic_writing_guidelines,
        template_name=template_name,
        author_name=author_name,
        author_tone=author_tone,
    )
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    last_error: str | None = None

    for attempt in range(max_retries):
        try:
            prompt = base_prompt + _build_retry_guidance(last_error)
            response = client.models.generate_content(
                model=config.GEMINI_CONTENT_MODEL,
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
                    attempt + 1,
                    word_count,
                    config.MIN_BODY_WORDS,
                )
                last_error = f"short:{word_count}"
                if attempt < max_retries - 1:
                    continue
                return None

            post = _normalize_generated_post(data)
            blocked = _contains_blocked_mentions(post)
            if blocked:
                logger.warning(
                    "Attempt %d: post contains blocked term '%s', retrying/aborting",
                    attempt + 1,
                    blocked,
                )
                last_error = f"blocked:{blocked}"
                if attempt < max_retries - 1:
                    continue
                return None
            logger.info("Artículo generado: '%s' (%d palabras)", post.title, word_count)
            return post

        except Exception as exc:
            logger.warning("Content generation attempt %d failed: %s", attempt + 1, exc)
            last_error = f"exception:{type(exc).__name__}"
            if attempt < max_retries - 1:
                continue

    logger.error("Failed to generate content after %d attempts", max_retries)
    return None


if __name__ == "__main__":
    config.setup_logging()
    config.validate()
    test = SearchResult(
        title="Nueva escuela Montessori abre en Europa",
        url="https://example.com/noticia",
        snippet="Una nueva escuela con método Montessori abrirá sus puertas para el ciclo 2026.",
    )
    post = generate_post(test)
    if post:
        print(f"Title: {post.title}")
        print(f"Excerpt: {post.excerpt}")
        print(f"Tags: {post.tags}")
        print(f"Image prompt: {post.image_prompt}")
        print(f"Body preview: {post.body[:300]}...")
