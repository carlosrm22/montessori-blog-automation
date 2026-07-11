"""Controlled article-to-training routing and HTML enrichment."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import unquote, urlencode, urlparse, urlsplit

from bs4 import BeautifulSoup, NavigableString

import config


ROUTES = {
    "nido": ("nido", "/diplomados/nido-comunidad-infantil/", "Nido y Comunidad Infantil"),
    "casa": ("casa", "/diplomados/casa-de-ninos/", "Casa de Niños"),
    "taller": ("taller", "/diplomados/taller-i-ii/", "Taller I y II"),
    "cosmica": ("cosmica", "/diplomados/educacion-cosmica/", "Educación Cósmica"),
    "neuro": ("neuro", "/diplomados/neuroeducacion/", "Neuroeducación"),
    "general_training": ("general_training", "/diplomados/", "formación como Guía Montessori"),
}

CONTEXT_COPY = (
    (
        "Si deseas profundizar profesionalmente en este tema, ",
        "consulta la formación en {label}",
        " de la Asociación Montessori de México.",
    ),
    (
        "Para llevar este tema a una preparación profesional, revisa ",
        "el programa de {label}",
        " de la Asociación Montessori de México.",
    ),
    (
        "Quienes busquen una ruta formativa relacionada pueden conocer ",
        "la propuesta de {label}",
        " de la Asociación Montessori de México.",
    ),
)

FUNNEL_MARKER_PREFIX = "ammac-training-"
FUNNEL_MARKER_ATTRIBUTES = frozenset({"data-program-id", "data-cta-position"})
C0_AND_SPACE = "".join(chr(codepoint) for codepoint in range(0x21))
SEMANTICALLY_UNSAFE_ELEMENTS = frozenset(
    {
        "template",
        "noscript",
        "script",
        "style",
        "textarea",
        "title",
        "select",
        "option",
        "head",
    }
)


@dataclass(frozen=True)
class ConversionDecision:
    intent: str
    relevance: str
    program_id: str
    destination_path: str
    destination_url: str
    attributed_url: str
    label: str
    post_slug: str
    post_title: str
    cta_level: str


def resolve_conversion_decision(
    intent: str,
    relevance: str,
    post_slug: str,
    post_title: str,
) -> ConversionDecision:
    clean_intent = str(intent or "").strip().lower()
    clean_relevance = str(relevance or "").strip().lower()
    route = ROUTES.get(clean_intent)
    if route is None or clean_relevance not in {"high", "medium"}:
        return ConversionDecision(
            intent="editorial",
            relevance="low",
            program_id="",
            destination_path="",
            destination_url="",
            attributed_url="",
            label="",
            post_slug=post_slug,
            post_title=post_title,
            cta_level="none",
        )

    program_id, path, label = route
    destination_url = f"{config.CERTIFICATION_SITE_URL}{path}"
    query = urlencode(
        {
            "utm_source": "montessorimexico.org",
            "utm_medium": "referral",
            "utm_campaign": "guia_montessori",
            "utm_content": post_slug,
            "utm_term": clean_intent,
        }
    )
    return ConversionDecision(
        intent=clean_intent,
        relevance=clean_relevance,
        program_id=program_id,
        destination_path=path,
        destination_url=destination_url,
        attributed_url=f"{destination_url}?{query}",
        label=label,
        post_slug=post_slug,
        post_title=post_title,
        cta_level=clean_relevance,
    )


def _contextual_paragraph(soup: BeautifulSoup, decision: ConversionDecision):
    digest = hashlib.sha256(
        f"{decision.intent}:{decision.post_slug}".encode("utf-8")
    ).digest()
    prefix, anchor_copy, suffix = CONTEXT_COPY[digest[0] % len(CONTEXT_COPY)]
    paragraph = soup.new_tag("p")
    paragraph["class"] = ["ammac-training-context"]
    paragraph.append(prefix)
    link = soup.new_tag("a", href=decision.attributed_url)
    link["class"] = ["ammac-training-link"]
    link["data-program-id"] = decision.program_id
    link["data-cta-position"] = "contextual"
    link.string = anchor_copy.format(label=decision.label)
    paragraph.append(link)
    paragraph.append(suffix)
    return paragraph


def strip_uncontrolled_commercial_links(html: str) -> tuple[str, int]:
    """Remove model-authored links to the commercial host while preserving text."""
    soup = BeautifulSoup(html or "", "html.parser")
    removed = _strip_uncontrolled_commercial_links(soup)
    return str(soup), removed


def _normalize_special_url(href: str) -> str:
    normalized = href.strip(C0_AND_SPACE)
    normalized = normalized.replace("\t", "").replace("\n", "").replace("\r", "")
    normalized = normalized.replace("\\", "/")

    lowered = normalized.lower()
    for scheme in ("https:", "http:"):
        if lowered.startswith(scheme):
            authority = normalized[len(scheme) :].lstrip("/")
            return f"{scheme}//{authority}"

    if normalized.startswith("//"):
        return f"//{normalized.lstrip('/')}"
    return normalized


def _canonicalize_host(encoded_host: str) -> str:
    host = unquote(encoded_host, errors="strict").lower()
    return host[:-1] if host.endswith(".") else host


def _malformed_authority_host(normalized_href: str) -> str | None:
    lowered = normalized_href.lower()
    if lowered.startswith("//"):
        authority = normalized_href[2:]
    elif lowered.startswith(("https://", "http://")):
        authority = normalized_href[normalized_href.index(":") + 3 :]
    else:
        return None

    authority = authority.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if authority.startswith("["):
        authority = authority[1:]
    if authority.endswith("]"):
        authority = authority[:-1]
    try:
        return _canonicalize_host(authority)
    except UnicodeError:
        return None


def _strip_uncontrolled_commercial_links(soup: BeautifulSoup) -> int:
    allowed_host = urlparse(config.CERTIFICATION_SITE_URL).hostname
    commercial_hosts = {allowed_host, f"www.{allowed_host}"}
    removed = 0
    for anchor in soup.find_all("a", href=True):
        normalized_href = _normalize_special_url(str(anchor.get("href") or ""))
        try:
            encoded_host = urlsplit(normalized_href).hostname
            host = _canonicalize_host(encoded_host) if encoded_host is not None else None
        except (UnicodeError, ValueError):
            host = _malformed_authority_host(normalized_href)
        if host in commercial_hosts:
            anchor.unwrap()
            removed += 1
    return removed


def _final_cta(soup: BeautifulSoup, decision: ConversionDecision):
    section = soup.new_tag("section")
    section["class"] = ["ammac-training-cta"]
    section["aria-label"] = "Formación Montessori relacionada"

    heading = soup.new_tag("h2")
    heading.string = f"Da el siguiente paso en {decision.label}"
    section.append(heading)

    body = soup.new_tag("p")
    body.string = (
        "Conoce la modalidad en línea, duración, acompañamiento y proceso de "
        "inscripción de este programa de AMMAC."
    )
    section.append(body)

    primary = soup.new_tag("a", href=decision.attributed_url)
    primary["class"] = ["ammac-training-cta-primary"]
    primary["data-program-id"] = decision.program_id
    primary["data-cta-position"] = "final"
    primary.string = "Conocer el programa"
    section.append(primary)

    message = (
        f"Hola, me interesa {decision.label}. Llegué desde el artículo "
        f"«{decision.post_title}». ¿Me pueden orientar?"
    )
    whatsapp = soup.new_tag(
        "a",
        href=(
            f"https://wa.me/{config.WHATSAPP_PHONE}?"
            f"{urlencode({'text': message})}"
        ),
    )
    whatsapp["class"] = ["ammac-training-cta-whatsapp"]
    whatsapp["data-program-id"] = decision.program_id
    whatsapp["data-cta-position"] = "final_whatsapp"
    whatsapp.string = "Preguntar por WhatsApp"
    section.append(whatsapp)
    return section


def _is_funnel_marker(element) -> bool:
    return any(
        str(class_name).startswith(FUNNEL_MARKER_PREFIX)
        for class_name in element.get("class", [])
    )


def _normalize_existing_funnel_content(soup: BeautifulSoup) -> None:
    for element in soup.find_all(True):
        if _is_funnel_marker(element):
            continue
        for attribute in FUNNEL_MARKER_ATTRIBUTES:
            element.attrs.pop(attribute, None)

    marked_elements = [
        element for element in soup.find_all(True) if _is_funnel_marker(element)
    ]
    marked_anchors = [element for element in marked_elements if element.name == "a"]

    ancestor_anchors = []
    seen_ancestor_anchors = set()
    for element in marked_elements:
        for ancestor in element.parents:
            if (
                ancestor.name == "a"
                and not _is_funnel_marker(ancestor)
                and id(ancestor) not in seen_ancestor_anchors
            ):
                ancestor_anchors.append(ancestor)
                seen_ancestor_anchors.add(id(ancestor))

    for anchor in ancestor_anchors:
        if anchor.parent is not None:
            anchor.unwrap()

    marked_non_anchors = {
        id(element) for element in marked_elements if element.name != "a"
    }

    for element in marked_elements:
        if element.name == "a" or element.parent is None:
            continue
        if any(id(parent) in marked_non_anchors for parent in element.parents):
            continue
        element.decompose()

    for element in marked_anchors:
        if element.parent is not None:
            element.replace_with(NavigableString(element.get_text()))

    _strip_uncontrolled_commercial_links(soup)


def _is_hidden(element) -> bool:
    attributes = getattr(element, "attrs", {})
    if "hidden" in attributes or "inert" in attributes:
        return True
    if str(attributes.get("aria-hidden", "")).strip().lower() == "true":
        return True
    return bool(str(attributes.get("style", "")).strip())


def _is_semantically_unsafe(element) -> bool:
    if element.name in SEMANTICALLY_UNSAFE_ELEMENTS:
        return True
    return element.name in {"details", "dialog"} and not element.has_attr("open")


def _is_safe_insertion_target(element) -> bool:
    return all(
        ancestor.name != "a"
        and not _is_hidden(ancestor)
        and not _is_semantically_unsafe(ancestor)
        for ancestor in (element, *element.parents)
    )


def _safe_root(soup: BeautifulSoup):
    if soup.body is not None and _is_safe_insertion_target(soup.body):
        return soup.body
    return soup


def _canonicalize_decision(decision: ConversionDecision) -> ConversionDecision:
    try:
        return resolve_conversion_decision(
            decision.intent,
            decision.relevance,
            decision.post_slug,
            decision.post_title,
        )
    except Exception:
        return resolve_conversion_decision("", "", "", "")


def apply_conversion_funnel(
    html: str,
    decision: ConversionDecision,
) -> tuple[str, dict[str, object]]:
    soup = BeautifulSoup(html or "", "html.parser")
    _normalize_existing_funnel_content(soup)
    canonical_decision = _canonicalize_decision(decision)

    if not config.CONVERSION_CTA_ENABLED or canonical_decision.cta_level not in {
        "medium",
        "high",
    }:
        return str(soup), {
            "cta_level": "none",
            "contextual_links": 0,
            "final_blocks": 0,
        }

    contextual = _contextual_paragraph(soup, canonical_decision)
    paragraphs = [
        paragraph
        for paragraph in soup.find_all("p")
        if _is_safe_insertion_target(paragraph)
    ]
    if len(paragraphs) >= 2:
        paragraphs[1].insert_after(contextual)
    elif paragraphs:
        paragraphs[0].insert_after(contextual)
    else:
        _safe_root(soup).insert(0, contextual)

    final_blocks = 0
    if canonical_decision.cta_level == "high":
        _safe_root(soup).append(_final_cta(soup, canonical_decision))
        final_blocks = 1

    return str(soup), {
        "cta_level": canonical_decision.cta_level,
        "contextual_links": 1,
        "final_blocks": final_blocks,
    }
