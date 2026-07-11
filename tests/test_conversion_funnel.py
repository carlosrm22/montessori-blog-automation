import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

import config
from conversion_funnel import (
    apply_conversion_funnel,
    resolve_conversion_decision,
    strip_uncontrolled_commercial_links,
)


ARTICLE = "<p>Introducción editorial.</p><p>Casa de Niños y observación.</p><h2>Práctica</h2>"


class ConversionFunnelTests(unittest.TestCase):
    def _assert_invalid_certification_origin(self, origin):
        with patch("config._get_required"), patch.multiple(
            config,
            SEARCH_PROVIDER="brave",
            BRAVE_SEARCH_COUNT=1,
            WP_IMAGE_WIDTH=1200,
            WP_IMAGE_HEIGHT=630,
            WP_IMAGE_QUALITY=90,
            MIN_BODY_WORDS=600,
            SOURCE_FETCH_MAX_CHARS=15000,
            LINK_CHECK_TIMEOUT=8,
            RECENT_POSTS_GALLERY_COUNT=4,
            PREFERRED_EXTERNAL_LINK_EVERY=3,
            WHATSAPP_PHONE="5215548885013",
            PREFERRED_EXTERNAL_LINKS=(),
            TOPICS_MAX_POSTS_PER_RUN=1,
            MIN_DRAFT_BUFFER=0,
            MAX_DRAFT_BACKLOG=0,
            PUBLISH_INTERVAL_DAYS=7,
            TRUSEO_MIN_SCORE=70,
            HEADLINE_MIN_SCORE=65,
            POST_TITLE_MAX_LEN=60,
            SOCIAL_TITLE_MAX_LEN=60,
            SOCIAL_DESCRIPTION_MAX_LEN=155,
            FOCUS_KEYPHRASE_MAX_WORDS=5,
            SITE_TITLE="Asociaci\u00f3n Montessori de M\u00e9xico",
            TITLE_SEPARATOR="|",
            BRAND_KIT="ammac",
            CERTIFICATION_SITE_URL=origin,
        ):
            with self.assertRaises(SystemExit):
                config.validate()

    def test_routes_only_known_intent_with_attribution(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observación en Casa"
        )
        self.assertEqual(decision.destination_path, "/diplomados/casa-de-ninos/")
        query = parse_qs(urlparse(decision.attributed_url).query)
        self.assertEqual(query["utm_source"], ["montessorimexico.org"])
        self.assertEqual(query["utm_medium"], ["referral"])
        self.assertEqual(query["utm_campaign"], ["guia_montessori"])
        self.assertEqual(query["utm_content"], ["observacion-casa"])
        self.assertEqual(query["utm_term"], ["casa"])

    def test_general_training_routes_to_the_hub(self):
        decision = resolve_conversion_decision(
            "general_training", "high", "ser-guia", "Cómo ser Guía Montessori"
        )
        self.assertEqual(decision.program_id, "general_training")
        self.assertEqual(decision.destination_path, "/diplomados/")

    def test_medium_adds_one_contextual_link_and_no_cta_block(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observación en Casa"
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            html, stats = apply_conversion_funnel(ARTICLE, decision)
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(len(soup.select("a.ammac-training-link")), 1)
        self.assertEqual(len(soup.select("section.ammac-training-cta")), 0)
        self.assertEqual(stats["cta_level"], "medium")

    def test_high_adds_context_link_and_single_final_block(self):
        decision = resolve_conversion_decision(
            "casa", "high", "ser-guia-casa", "Cómo ser Guía de Casa"
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            html, _ = apply_conversion_funnel(ARTICLE, decision)
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(len(soup.select("a.ammac-training-link")), 1)
        self.assertEqual(len(soup.select("section.ammac-training-cta")), 1)
        self.assertEqual(len(soup.select("section.ammac-training-cta a")), 2)

    def test_high_rebuilds_spoofed_and_duplicate_markers(self):
        decision = resolve_conversion_decision(
            "casa", "high", "ser-guia-casa", "C\u00f3mo ser Gu\u00eda de Casa"
        )
        html = (
            '<p>Introducci\u00f3n editorial.</p><p>Casa de Ni\u00f1os.</p>'
            '<a class="ammac-training-link" data-program-id="invented" '
            'data-cta-position="contextual" href="https://attacker.example">Spoof</a>'
            '<a class="ammac-training-link" data-program-id="casa" '
            'data-cta-position="contextual" href="https://certificacionmontessori.com/wrong">Duplicado</a>'
            '<section class="ammac-training-cta"><a href="https://attacker.example">CTA falsa</a></section>'
            '<section class="ammac-training-cta"><a href="https://attacker.example">CTA falsa 2</a></section>'
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, stats = apply_conversion_funnel(html, decision)
        soup = BeautifulSoup(output, "html.parser")
        links = soup.select("a.ammac-training-link")
        final_blocks = soup.select("section.ammac-training-cta")

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["href"], decision.attributed_url)
        self.assertEqual(links[0]["data-program-id"], decision.program_id)
        self.assertEqual(links[0]["data-cta-position"], "contextual")
        self.assertEqual(len(final_blocks), 1)
        self.assertEqual(len(final_blocks[0].select("a")), 2)
        self.assertEqual(stats["contextual_links"], 1)
        self.assertEqual(stats["final_blocks"], 1)

    def test_medium_removes_injected_final_cta_and_rebuilds_contextual_link(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observaci\u00f3n en Casa"
        )
        html = (
            '<p>Introducci\u00f3n editorial.</p><p>Casa de Ni\u00f1os.</p>'
            '<a class="ammac-training-link" data-program-id="invented" '
            'data-cta-position="contextual" href="https://attacker.example">Spoof</a>'
            '<section class="ammac-training-cta"><a href="https://attacker.example">CTA falsa</a></section>'
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, stats = apply_conversion_funnel(html, decision)
        soup = BeautifulSoup(output, "html.parser")
        links = soup.select("a.ammac-training-link")

        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["href"], decision.attributed_url)
        self.assertEqual(len(soup.select("section.ammac-training-cta")), 0)
        self.assertEqual(stats["contextual_links"], 1)
        self.assertEqual(stats["final_blocks"], 0)

    def test_valid_controlled_insertion_is_idempotent(self):
        decision = resolve_conversion_decision(
            "casa", "high", "ser-guia-casa", "C\u00f3mo ser Gu\u00eda de Casa"
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            inserted, _ = apply_conversion_funnel(ARTICLE, decision)
            output, stats = apply_conversion_funnel(inserted, decision)

        self.assertEqual(output, inserted)
        self.assertEqual(stats["contextual_links"], 1)
        self.assertEqual(stats["final_blocks"], 1)

    def test_high_rebuilds_when_an_orphan_primary_cta_marker_is_present(self):
        decision = resolve_conversion_decision(
            "casa", "high", "ser-guia-casa", "C\u00f3mo ser Gu\u00eda de Casa"
        )
        orphan = (
            '<aside><a class="ammac-training-cta-primary" '
            'data-program-id="invented" data-cta-position="final" '
            'href="https://attacker.example/primary">Oferta falsa</a></aside>'
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            inserted, _ = apply_conversion_funnel(ARTICLE, decision)
            output, stats = apply_conversion_funnel(f"{inserted}{orphan}", decision)

        soup = BeautifulSoup(output, "html.parser")
        self.assertEqual(len(soup.select("section.ammac-training-cta")), 1)
        self.assertEqual(len(soup.select("a.ammac-training-cta-primary")), 1)
        self.assertNotIn("https://attacker.example/primary", output)
        self.assertEqual(stats["contextual_links"], 1)
        self.assertEqual(stats["final_blocks"], 1)

    def test_medium_rebuilds_when_an_orphan_whatsapp_cta_marker_is_present(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observaci\u00f3n en Casa"
        )
        orphan = (
            '<div><a class="ammac-training-cta-whatsapp" '
            'data-program-id="invented" data-cta-position="final_whatsapp" '
            'href="https://attacker.example/whatsapp">WhatsApp falso</a></div>'
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            inserted, _ = apply_conversion_funnel(ARTICLE, decision)
            output, stats = apply_conversion_funnel(f"{inserted}{orphan}", decision)

        soup = BeautifulSoup(output, "html.parser")
        self.assertEqual(len(soup.select("section.ammac-training-cta")), 0)
        self.assertEqual(len(soup.select("a.ammac-training-cta-whatsapp")), 0)
        self.assertNotIn("https://attacker.example/whatsapp", output)
        self.assertEqual(stats["contextual_links"], 1)
        self.assertEqual(stats["final_blocks"], 0)

    def test_low_relevance_changes_nothing_even_when_enabled(self):
        with patch("config.CONVERSION_CTA_ENABLED", True):
            decision = resolve_conversion_decision("casa", "low", "post", "Post")
            html, stats = apply_conversion_funnel(ARTICLE, decision)
        self.assertEqual(html, ARTICLE)
        self.assertEqual(stats["cta_level"], "none")

    def test_invalid_intent_changes_nothing_even_when_enabled(self):
        with patch("config.CONVERSION_CTA_ENABLED", True):
            decision = resolve_conversion_decision("invented", "high", "post", "Post")
            html, stats = apply_conversion_funnel(ARTICLE, decision)
        self.assertEqual(html, ARTICLE)
        self.assertEqual(stats["cta_level"], "none")

    def test_disabled_flag_changes_nothing_for_a_valid_decision(self):
        with patch("config.CONVERSION_CTA_ENABLED", False):
            decision = resolve_conversion_decision("casa", "high", "post", "Post")
            html, stats = apply_conversion_funnel(ARTICLE, decision)
        self.assertEqual(html, ARTICLE)
        self.assertEqual(stats["cta_level"], "none")

    def test_strips_only_uncontrolled_commercial_links(self):
        html = (
            '<p><a href="https://certificacionmontessori.com/inventado/">Inventado</a> '
            '<a href="https://fuente.example/articulo">Fuente</a></p>'
        )
        cleaned, removed = strip_uncontrolled_commercial_links(html)
        soup = BeautifulSoup(cleaned, "html.parser")
        self.assertEqual(removed, 1)
        self.assertEqual(len(soup.select("a")), 1)
        self.assertEqual(soup.a["href"], "https://fuente.example/articulo")

    def test_validate_rejects_noncanonical_certification_origins(self):
        invalid_origins = (
            "https://@certificacionmontessori.com",
            "https://user@certificacionmontessori.com",
            "https://certificacionmontessori.com:443",
            "https://certificacionmontessori.com:",
            "https://certificacionmontessori.com:not-a-port",
            "https://certificacionmontessori.com/path",
            "https://certificacionmontessori.com?query=value",
            "https://certificacionmontessori.com#fragment",
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin):
                self._assert_invalid_certification_origin(origin)


if __name__ == "__main__":
    unittest.main()
