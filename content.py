"""Genera artículo original usando Gemini 2.0 Flash."""

import json
import logging
from dataclasses import dataclass

from google import genai
from jinja2 import Environment, FileSystemLoader

import config
from search import SearchResult

logger = logging.getLogger(__name__)


@dataclass
class GeneratedPost:
    title: str
    body: str
    excerpt: str
    categories: list[str]
    tags: list[str]
    seo_title: str
    seo_description: str
    image_prompt: str


def _render_prompt(article: SearchResult) -> str:
    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR))
    template = env.get_template("post_prompt.txt")
    return template.render(
        title=article.title, url=article.url, snippet=article.snippet
    )


def _count_words_html(html: str) -> int:
    """Rough word count stripping HTML tags."""
    from bs4 import BeautifulSoup
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return len(text.split())


def generate_post(article: SearchResult, max_retries: int = 2) -> GeneratedPost | None:
    """Generate an original blog post from a source article."""
    prompt = _render_prompt(article)
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
            )
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            data = json.loads(text)
            body = data.get("body", "")
            word_count = _count_words_html(body)

            if word_count < 200:
                logger.warning(
                    "Attempt %d: body too short (%d words), aborting",
                    attempt + 1, word_count,
                )
                if attempt < max_retries - 1:
                    continue
                return None

            post = GeneratedPost(
                title=data["title"],
                body=body,
                excerpt=data.get("excerpt", ""),
                categories=data.get("categories", ["Educación Montessori"]),
                tags=data.get("tags", []),
                seo_title=data.get("seo_title", data["title"]),
                seo_description=data.get("seo_description", ""),
                image_prompt=data.get("image_prompt", ""),
            )
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
