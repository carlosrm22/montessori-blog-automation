"""Local SEO scoring rules inspired by AIOSEO public checklists."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from urllib.parse import urlparse

from bs4 import BeautifulSoup


@dataclass
class CheckResult:
    key: str
    passed: bool
    details: str
    value: object | None = None
    target: object | None = None
    weight: float = 1.0


@dataclass
class ScoreReport:
    score: int
    checks: list[CheckResult]
    extras: dict[str, object]

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "checks": [asdict(c) for c in self.checks],
            "extras": self.extras,
        }


def _score_from_checks(checks: list[CheckResult]) -> int:
    total_weight = sum(c.weight for c in checks) or 1.0
    earned_weight = sum(c.weight for c in checks if c.passed)
    return int(round((earned_weight / total_weight) * 100))


def _normalize_text(text: str, strip_accents: bool = False) -> str:
    normalized = " ".join((text or "").strip().lower().split())
    if strip_accents:
        normalized = "".join(
            ch for ch in unicodedata.normalize("NFD", normalized)
            if unicodedata.category(ch) != "Mn"
        )
    return normalized


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^A-Za-z0-9\s-]", "", normalized).strip().lower()
    slug = re.sub(r"[-\s]+", "-", normalized).strip("-")
    return slug[:90]


def build_slug(value: str) -> str:
    """Public helper to generate a WordPress-like slug for SEO checks."""
    return _slugify(value)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\wáéíóúüñ]+\b", text.lower(), flags=re.UNICODE))


def _extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?]+", text) if part.strip()]


def _first_sentence(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    first_p = soup.find("p")
    if first_p is None:
        return ""
    text = first_p.get_text(" ", strip=True)
    sentences = _split_sentences(text)
    return sentences[0] if sentences else text


def _count_internal_external_links(html: str, site_domain: str) -> tuple[int, int]:
    soup = BeautifulSoup(html or "", "html.parser")
    internal = 0
    external = 0
    domain = (site_domain or "").strip().lower()

    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue
        if href.startswith("/"):
            internal += 1
            continue
        parsed = urlparse(href)
        if not parsed.netloc:
            internal += 1
            continue
        link_domain = parsed.netloc.lower()
        if domain and (link_domain == domain or link_domain.endswith(f".{domain}")):
            internal += 1
        else:
            external += 1
    return internal, external


def _has_media(html: str) -> bool:
    soup = BeautifulSoup(html or "", "html.parser")
    return bool(soup.find(["img", "video", "iframe"]))


def _paragraphs_over_120_words(html: str) -> int:
    soup = BeautifulSoup(html or "", "html.parser")
    count = 0
    for paragraph in soup.find_all("p"):
        if _word_count(paragraph.get_text(" ", strip=True)) > 120:
            count += 1
    return count


def _has_h2_or_h3(html: str) -> bool:
    soup = BeautifulSoup(html or "", "html.parser")
    return bool(soup.find(["h2", "h3"]))


def _keyword_occurrences(text: str, phrase: str, strict_phrase: bool = True) -> int:
    content = _normalize_text(text, strip_accents=False)
    keyword = _normalize_text(phrase, strip_accents=False)
    if not keyword:
        return 0
    if strict_phrase:
        pattern = r"(?<!\w)" + re.escape(keyword) + r"(?!\w)"
        return len(re.findall(pattern, content, flags=re.UNICODE))
    return content.count(keyword)


def _keyword_in_subheadings(html: str, phrase: str, strict_phrase: bool = True) -> bool:
    soup = BeautifulSoup(html or "", "html.parser")
    for heading in soup.find_all(["h2", "h3"]):
        if _keyword_occurrences(heading.get_text(" ", strip=True), phrase, strict_phrase) > 0:
            return True
    return False


def _keyword_in_img_alt(html: str, phrase: str, strict_phrase: bool = True) -> bool:
    soup = BeautifulSoup(html or "", "html.parser")
    for image in soup.find_all("img"):
        alt_text = image.get("alt") or ""
        if _keyword_occurrences(alt_text, phrase, strict_phrase) > 0:
            return True
    return False


def analyze_truseo(
    *,
    html: str,
    post_title: str,
    seo_title: str,
    meta_description: str,
    slug: str,
    focus_keyphrase: str,
    site_domain: str,
    og_title: str = "",
    og_description: str = "",
    twitter_title: str = "",
    twitter_description: str = "",
    social_image_source: str = "",
    post_title_max_len: int = 60,
    strict_phrase: bool = True,
) -> dict[str, ScoreReport]:
    text = _extract_text_from_html(html)
    word_count = _word_count(text)
    internal_links, external_links = _count_internal_external_links(html, site_domain)
    post_title_len = len((post_title or "").strip())
    seo_title_len = len((seo_title or "").strip())
    meta_desc_len = len((meta_description or "").strip())
    paragraphs_too_long = _paragraphs_over_120_words(html)
    has_h2_h3 = _has_h2_or_h3(html)
    has_images_or_video = _has_media(html)
    sentences = _split_sentences(text)
    avg_sentence_words = (
        sum(_word_count(sentence) for sentence in sentences) / len(sentences)
        if sentences
        else 0.0
    )

    page_checks = [
        CheckResult(
            key="post_title_length",
            passed=post_title_len <= post_title_max_len,
            details="Título del post dentro de longitud recomendada.",
            value=post_title_len,
            target=f"<= {post_title_max_len}",
        ),
        CheckResult(
            key="meta_description_length",
            passed=120 <= meta_desc_len <= 160,
            details="Meta description entre 120 y 160 caracteres.",
            value=meta_desc_len,
            target="120-160",
        ),
        CheckResult(
            key="content_length",
            passed=word_count >= 300,
            details="Contenido con al menos 300 palabras.",
            value=word_count,
            target=">=300",
        ),
        CheckResult(
            key="internal_links",
            passed=internal_links >= 1,
            details="Al menos 1 enlace interno.",
            value=internal_links,
            target=">=1",
        ),
        CheckResult(
            key="external_links",
            passed=external_links >= 1,
            details="Al menos 1 enlace externo recomendado.",
            value=external_links,
            target=">=1",
            weight=0.5,
        ),
        CheckResult(
            key="seo_title_length",
            passed=40 <= seo_title_len <= 60,
            details="SEO title entre 40 y 60 caracteres.",
            value=seo_title_len,
            target="40-60",
        ),
        CheckResult(
            key="has_images_or_video",
            passed=has_images_or_video,
            details="Incluye imagen o video en el contenido.",
            value=has_images_or_video,
            target=True,
        ),
        CheckResult(
            key="paragraph_length",
            passed=paragraphs_too_long == 0,
            details="Sin párrafos mayores a 120 palabras.",
            value=paragraphs_too_long,
            target=0,
        ),
        CheckResult(
            key="subheading_distribution",
            passed=(word_count <= 300) or has_h2_h3,
            details="Si el contenido supera 300 palabras, debe incluir H2/H3.",
            value={"word_count": word_count, "has_h2_h3": has_h2_h3},
            target="H2/H3 si >300 palabras",
        ),
        CheckResult(
            key="sentence_length",
            passed=(not sentences) or (avg_sentence_words <= 20),
            details="Promedio de oración cercano a 20 palabras.",
            value=round(avg_sentence_words, 2),
            target="<=20",
        ),
    ]

    social_image_ok = (social_image_source or "").strip().lower() in {"featured_media", "custom_url"}
    page_checks.extend(
        [
            CheckResult(
                key="og_title_present",
                passed=bool((og_title or "").strip()) and len((og_title or "").strip()) <= 60,
                details="Open Graph title presente y <= 60 caracteres.",
            ),
            CheckResult(
                key="og_description_present",
                passed=bool((og_description or "").strip()) and len((og_description or "").strip()) <= 155,
                details="Open Graph description presente y <= 155 caracteres.",
            ),
            CheckResult(
                key="twitter_title_present",
                passed=bool((twitter_title or "").strip()) and len((twitter_title or "").strip()) <= 60,
                details="Twitter title presente y <= 60 caracteres.",
            ),
            CheckResult(
                key="twitter_description_present",
                passed=bool((twitter_description or "").strip()) and len((twitter_description or "").strip()) <= 155,
                details="Twitter description presente y <= 155 caracteres.",
            ),
            CheckResult(
                key="social_image_source",
                passed=social_image_ok,
                details="Origen de imagen social definido (featured_media/custom_url).",
                value=social_image_source,
                target="featured_media|custom_url",
            ),
        ]
    )
    page_score = _score_from_checks(page_checks)

    keyword = (focus_keyphrase or "").strip()
    content_occurrences = _keyword_occurrences(text, keyword, strict_phrase)
    density = (content_occurrences / max(word_count, 1)) * 100
    first_sentence = _first_sentence(html)
    first_title_chunk = " ".join((seo_title or "").split()[:10])

    keyword_checks = [
        CheckResult(
            key="keyword_in_meta_description",
            passed=_keyword_occurrences(meta_description, keyword, strict_phrase) > 0,
            details="Focus keyword en meta description.",
        ),
        CheckResult(
            key="keyword_in_seo_title",
            passed=_keyword_occurrences(seo_title, keyword, strict_phrase) > 0,
            details="Focus keyword en SEO title.",
        ),
        CheckResult(
            key="keyword_in_url",
            passed=_keyword_occurrences(slug, keyword, strict_phrase) > 0,
            details="Focus keyword en URL/slug.",
        ),
        CheckResult(
            key="keyword_in_introduction",
            passed=_keyword_occurrences(first_sentence, keyword, strict_phrase) > 0,
            details="Focus keyword en introducción (primera oración).",
        ),
        CheckResult(
            key="keyword_in_subheadings",
            passed=_keyword_in_subheadings(html, keyword, strict_phrase),
            details="Focus keyword en H2/H3.",
        ),
        CheckResult(
            key="keyword_in_image_alt",
            passed=_keyword_in_img_alt(html, keyword, strict_phrase),
            details="Focus keyword en alt de imagen.",
        ),
        CheckResult(
            key="keyword_in_content",
            passed=content_occurrences > 0,
            details="Focus keyword en contenido.",
        ),
        CheckResult(
            key="keyword_at_beginning_of_seo_title",
            passed=_keyword_occurrences(first_title_chunk, keyword, strict_phrase) > 0,
            details="Focus keyword al inicio del SEO title.",
        ),
        CheckResult(
            key="keyword_length",
            passed=len(keyword.split()) <= 5,
            details="Focus keyword con 5 palabras o menos.",
            value=len(keyword.split()),
            target="<=5",
        ),
        CheckResult(
            key="keyword_density",
            passed=content_occurrences > 0,
            details="Densidad calculada (sin rango oficial público).",
            value={
                "occurrences": content_occurrences,
                "density_percent": round(density, 3),
            },
            target=">0",
        ),
        CheckResult(
            key="keyword_in_og_description",
            passed=_keyword_occurrences(og_description, keyword, strict_phrase) > 0,
            details="Focus keyword en Open Graph description.",
        ),
        CheckResult(
            key="keyword_in_twitter_description",
            passed=_keyword_occurrences(twitter_description, keyword, strict_phrase) > 0,
            details="Focus keyword en Twitter description.",
        ),
    ]
    keyword_score = _score_from_checks(keyword_checks)

    overall_score = int(round((page_score + keyword_score) / 2))
    return {
        "page_analysis": ScoreReport(
            score=page_score,
            checks=page_checks,
            extras={
                "word_count": word_count,
                "internal_links": internal_links,
                "external_links": external_links,
            },
        ),
        "focus_keyword": ScoreReport(
            score=keyword_score,
            checks=keyword_checks,
            extras={"focus_keyphrase": keyword},
        ),
        "overall": ScoreReport(
            score=overall_score,
            checks=[],
            extras={"page_score": page_score, "focus_keyword_score": keyword_score},
        ),
    }


def analyze_headline(title: str, primary_keyword: str = "") -> ScoreReport:
    clean_title = (title or "").strip()
    words = re.findall(r"\b[\wáéíóúüñ]+\b", clean_title.lower(), flags=re.UNICODE)
    chars_without_spaces = len(re.sub(r"\s+", "", clean_title))
    word_count = len(words)
    first_chunk = " ".join(clean_title.lower().split()[:8])
    keyword = (primary_keyword or "").strip()

    checks = [
        CheckResult(
            key="character_count",
            passed=chars_without_spaces > 35,
            details="Más de 35 caracteres (sin espacios).",
            value=chars_without_spaces,
            target=">35",
        ),
        CheckResult(
            key="word_count",
            passed=word_count > 5,
            details="Más de 5 palabras.",
            value=word_count,
            target=">5",
        ),
        CheckResult(
            key="title_under_65_chars",
            passed=len(clean_title) <= 65,
            details="Titular bajo ~65 caracteres.",
            value=len(clean_title),
            target="<=65",
            weight=0.75,
        ),
    ]
    if keyword:
        checks.append(
            CheckResult(
                key="keyword_early",
                passed=_normalize_text(keyword) in _normalize_text(first_chunk),
                details="Keyword principal aparece temprano en titular.",
                value={"keyword": keyword, "first_chunk": first_chunk},
                target="keyword en primeras palabras",
                weight=1.25,
            )
        )

    lower_title = clean_title.lower()
    if re.search(r"^\s*(como|cómo)\s+", lower_title):
        headline_type = "how-to"
    elif re.search(r"\b\d+\b", lower_title):
        headline_type = "list"
    elif clean_title.endswith("?"):
        headline_type = "question"
    else:
        headline_type = "general"

    return ScoreReport(
        score=_score_from_checks(checks),
        checks=checks,
        extras={
            "headline_type_guess": headline_type,
            "beginning_words": words[:3],
            "ending_words": words[-3:] if words else [],
            "slug_preview": _slugify(clean_title),
        },
    )
