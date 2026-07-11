"""Controlled article-to-training routing and HTML enrichment."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from bs4 import BeautifulSoup

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
    allowed_host = urlparse(config.CERTIFICATION_SITE_URL).hostname
    removed = 0
    for anchor in soup.find_all("a", href=True):
        try:
            host = urlparse(str(anchor.get("href") or "").strip()).hostname
        except ValueError:
            host = None
        if host in {allowed_host, f"www.{allowed_host}"}:
            anchor.unwrap()
            removed += 1
    return str(soup), removed


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


def apply_conversion_funnel(
    html: str,
    decision: ConversionDecision,
) -> tuple[str, dict[str, object]]:
    if not config.CONVERSION_CTA_ENABLED or decision.cta_level == "none":
        return html, {"cta_level": "none", "contextual_links": 0, "final_blocks": 0}

    soup = BeautifulSoup(html or "", "html.parser")
    if soup.select_one(".ammac-training-link, .ammac-training-cta"):
        return str(soup), {
            "cta_level": decision.cta_level,
            "contextual_links": len(soup.select("a.ammac-training-link")),
            "final_blocks": len(soup.select("section.ammac-training-cta")),
        }

    contextual = _contextual_paragraph(soup, decision)
    paragraphs = soup.find_all("p")
    if len(paragraphs) >= 2:
        paragraphs[1].insert_after(contextual)
    elif paragraphs:
        paragraphs[0].insert_after(contextual)
    else:
        soup.insert(0, contextual)

    final_blocks = 0
    if decision.cta_level == "high":
        soup.append(_final_cta(soup, decision))
        final_blocks = 1

    return str(soup), {
        "cta_level": decision.cta_level,
        "contextual_links": 1,
        "final_blocks": final_blocks,
    }
