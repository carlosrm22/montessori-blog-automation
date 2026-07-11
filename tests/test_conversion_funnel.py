import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from conversion_funnel import (
    apply_conversion_funnel,
    resolve_conversion_decision,
    strip_uncontrolled_commercial_links,
)


ARTICLE = "<p>Introducción editorial.</p><p>Casa de Niños y observación.</p><h2>Práctica</h2>"


class ConversionFunnelTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
