import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

import config
from conversion_funnel import (
    ConversionDecision,
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

    def test_forged_high_decision_is_rebuilt_from_classifier_fields(self):
        forged = ConversionDecision(
            intent="casa",
            relevance="high",
            program_id="attacker-program",
            destination_path="/attacker-route/",
            destination_url="https://attacker.example/destination",
            attributed_url="https://attacker.example/tracked",
            label="Attacker label",
            post_slug="canonical-post",
            post_title="Canonical Post",
            cta_level="high",
        )
        canonical = resolve_conversion_decision(
            forged.intent, forged.relevance, forged.post_slug, forged.post_title
        )

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, stats = apply_conversion_funnel(ARTICLE, forged)

        soup = BeautifulSoup(output, "html.parser")
        commercial_links = soup.select(
            "a.ammac-training-link, a.ammac-training-cta-primary"
        )
        self.assertEqual(len(commercial_links), 2)
        self.assertTrue(
            all(link["href"] == canonical.attributed_url for link in commercial_links)
        )
        self.assertTrue(
            all(link["data-program-id"] == "casa" for link in commercial_links)
        )
        query = parse_qs(urlparse(commercial_links[0]["href"]).query)
        self.assertEqual(query["utm_content"], ["canonical-post"])
        self.assertEqual(query["utm_term"], ["casa"])
        self.assertIn("Casa de Niños", soup.get_text())
        self.assertNotIn("attacker", output.lower())
        self.assertEqual(stats["cta_level"], "high")

    def test_forged_invalid_decision_fails_closed(self):
        forged = ConversionDecision(
            intent="invented",
            relevance="high",
            program_id="attacker-program",
            destination_path="/attacker-route/",
            destination_url="https://attacker.example/destination",
            attributed_url="https://attacker.example/tracked",
            label="Attacker label",
            post_slug="post",
            post_title="Post",
            cta_level="high",
        )

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, stats = apply_conversion_funnel(ARTICLE, forged)

        self.assertEqual(output, ARTICLE)
        self.assertEqual(stats["cta_level"], "none")
        self.assertNotIn("ammac-training-", output)

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

    def test_two_run_output_is_byte_identical_for_medium_and_high(self):
        for relevance in ("medium", "high"):
            with self.subTest(relevance=relevance):
                decision = resolve_conversion_decision(
                    "casa", relevance, f"ser-guia-{relevance}", "C\u00f3mo ser Gu\u00eda"
                )
                dirty_html = (
                    f'{ARTICLE}<aside class="ammac-training-spoof">Falso</aside>'
                    '<a href="https://certificacionmontessori.com/inventado/">'
                    "Enlace no controlado</a>"
                )
                with patch("config.CONVERSION_CTA_ENABLED", True):
                    first, _ = apply_conversion_funnel(dirty_html, decision)
                    second, stats = apply_conversion_funnel(first, decision)

                self.assertEqual(second, first)
                self.assertEqual(stats["contextual_links"], 1)
                self.assertEqual(
                    stats["final_blocks"], 1 if relevance == "high" else 0
                )

    def test_generated_blocks_are_relocated_out_of_hidden_and_inert_ancestors(self):
        decision = resolve_conversion_decision(
            "casa", "high", "ser-guia-casa", "C\u00f3mo ser Gu\u00eda de Casa"
        )
        for unsafe_attribute in ("hidden", "inert"):
            with self.subTest(unsafe_attribute=unsafe_attribute):
                with patch("config.CONVERSION_CTA_ENABLED", True):
                    generated, _ = apply_conversion_funnel(ARTICLE, decision)

                soup = BeautifulSoup(generated, "html.parser")
                wrapper = soup.new_tag("div")
                wrapper[unsafe_attribute] = ""
                soup.insert(0, wrapper)
                wrapper.append(soup.select_one("p.ammac-training-context").extract())
                wrapper.append(soup.select_one("section.ammac-training-cta").extract())

                with patch("config.CONVERSION_CTA_ENABLED", True):
                    output, _ = apply_conversion_funnel(str(soup), decision)

                rebuilt = BeautifulSoup(output, "html.parser")
                for generated_element in rebuilt.select(
                    ".ammac-training-context, .ammac-training-cta"
                ):
                    self.assertFalse(
                        any(
                            ancestor.has_attr("hidden") or ancestor.has_attr("inert")
                            for ancestor in generated_element.parents
                        )
                    )

    def test_attacker_anchor_wrapping_marked_content_is_neutralized(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observaci\u00f3n en Casa"
        )
        hostile_url = "https://attacker.example/wrapper"
        html = (
            f'{ARTICLE}<a href="{hostile_url}">Texto anterior '
            '<span class="ammac-training-context">Bloque generado falso</span>'
            " texto posterior</a>"
        )

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, _ = apply_conversion_funnel(html, decision)

        soup = BeautifulSoup(output, "html.parser")
        self.assertIsNone(soup.find("a", href=hostile_url))
        self.assertIn("Texto anterior", soup.get_text())
        self.assertIn("texto posterior", soup.get_text())

    def test_contextual_insertion_skips_unsafe_paragraphs(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observaci\u00f3n en Casa"
        )
        html = (
            '<div hidden><p id="hidden">Oculto</p></div>'
            '<div aria-hidden="true"><p id="aria-hidden">Oculto ARIA</p></div>'
            '<div style="display: none"><p id="display-none">Sin display</p></div>'
            '<div style="visibility:hidden"><p id="visibility-hidden">Invisible</p></div>'
            '<div inert><p id="inert">Inerte</p></div>'
            '<a href="https://fuente.example"><p id="inside-anchor">Enlace</p></a>'
            '<p id="visible">Visible</p>'
        )

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, _ = apply_conversion_funnel(html, decision)

        soup = BeautifulSoup(output, "html.parser")
        contextual = soup.select_one("p.ammac-training-context")
        self.assertEqual(contextual.find_previous_sibling("p")["id"], "visible")

    def test_contextual_insertion_rejects_css_comment_obfuscation(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observación en Casa"
        )
        html = (
            '<div id="styled-hidden" style="display:/**/none">'
            '<p id="hidden-one">Oculto uno</p><p id="hidden-two">Oculto dos</p>'
            '</div><p id="visible">Visible</p>'
        )

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, _ = apply_conversion_funnel(html, decision)

        soup = BeautifulSoup(output, "html.parser")
        contextual = soup.select_one("p.ammac-training-context")
        self.assertIsNone(contextual.find_parent(id="styled-hidden"))
        self.assertEqual(contextual.find_previous_sibling("p")["id"], "visible")

    def test_contextual_insertion_skips_template_and_noscript(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observación en Casa"
        )
        html = (
            '<template><p id="template">Plantilla</p></template>'
            '<noscript><p id="noscript">Alternativa sin scripts</p></noscript>'
            '<p id="visible">Visible</p>'
        )

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, _ = apply_conversion_funnel(html, decision)

        soup = BeautifulSoup(output, "html.parser")
        contextual = soup.select_one("p.ammac-training-context")
        self.assertEqual(contextual.find_previous_sibling("p")["id"], "visible")
        self.assertIsNone(contextual.find_parent(["template", "noscript"]))

    def test_contextual_insertion_skips_closed_details_and_dialog(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observación en Casa"
        )
        html = (
            '<details><p id="closed-details">Detalles cerrados</p></details>'
            '<dialog><p id="closed-dialog">Diálogo cerrado</p></dialog>'
            '<p id="visible">Visible</p>'
        )

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, _ = apply_conversion_funnel(html, decision)

        soup = BeautifulSoup(output, "html.parser")
        contextual = soup.select_one("p.ammac-training-context")
        self.assertEqual(contextual.find_previous_sibling("p")["id"], "visible")
        self.assertIsNone(contextual.find_parent(["details", "dialog"]))

    def test_contextual_insertion_uses_safe_root_fallback(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observaci\u00f3n en Casa"
        )
        html = '<div hidden><p>Oculto</p></div><div inert><p>Inerte</p></div>'

        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, _ = apply_conversion_funnel(html, decision)

        soup = BeautifulSoup(output, "html.parser")
        contextual = soup.select_one("p.ammac-training-context")
        self.assertIs(contextual.parent, soup)
        self.assertIsNone(soup.html)
        self.assertIsNone(soup.body)
        self.assertFalse(
            any(
                ancestor.has_attr("hidden") or ancestor.has_attr("inert")
                for ancestor in contextual.parents
            )
        )

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

    def test_high_removes_malformed_marked_attribute_container_subtree(self):
        decision = resolve_conversion_decision(
            "casa", "high", "ser-guia-casa", "C\u00f3mo ser Gu\u00eda de Casa"
        )
        malformed = (
            '<aside class="ammac-training-malformed" data-cta-position="final">Contenido falso '
            '<a href="https://attacker.example/high">Oferta falsa</a></aside>'
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, stats = apply_conversion_funnel(f"{ARTICLE}{malformed}", decision)

        soup = BeautifulSoup(output, "html.parser")
        self.assertIsNone(soup.find("a", href="https://attacker.example/high"))
        self.assertNotIn("Contenido falso", soup.get_text())
        self.assertEqual(len(soup.select("a.ammac-training-link")), 1)
        self.assertEqual(len(soup.select("section.ammac-training-cta")), 1)
        self.assertEqual(stats["contextual_links"], 1)
        self.assertEqual(stats["final_blocks"], 1)

    def test_medium_removes_malformed_marked_attribute_container_subtree(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observaci\u00f3n en Casa"
        )
        malformed = (
            '<div class="ammac-training-malformed" data-program-id="invented">Contenido falso '
            '<a href="https://attacker.example/medium">Oferta falsa</a></div>'
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, stats = apply_conversion_funnel(f"{ARTICLE}{malformed}", decision)

        soup = BeautifulSoup(output, "html.parser")
        self.assertIsNone(soup.find("a", href="https://attacker.example/medium"))
        self.assertNotIn("Contenido falso", soup.get_text())
        self.assertEqual(len(soup.select("a.ammac-training-link")), 1)
        self.assertEqual(len(soup.select("section.ammac-training-cta")), 0)
        self.assertEqual(stats["contextual_links"], 1)
        self.assertEqual(stats["final_blocks"], 0)

    def test_removes_unknown_marker_class_container_subtree(self):
        decision = resolve_conversion_decision(
            "casa", "medium", "observacion-casa", "Observaci\u00f3n en Casa"
        )
        malformed = (
            '<nav class="ammac-training-invented">Navegaci\u00f3n falsa '
            '<a href="https://attacker.example/unknown">Oferta falsa</a></nav>'
        )
        with patch("config.CONVERSION_CTA_ENABLED", True):
            output, _ = apply_conversion_funnel(f"{ARTICLE}{malformed}", decision)

        soup = BeautifulSoup(output, "html.parser")
        self.assertIsNone(soup.find("a", href="https://attacker.example/unknown"))
        self.assertNotIn("Navegaci\u00f3n falsa", soup.get_text())
        self.assertFalse(
            any(
                class_name.startswith("ammac-training-")
                for element in soup.find_all(True)
                for class_name in element.get("class", [])
                if class_name not in {"ammac-training-context", "ammac-training-link"}
            )
        )

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

    def test_disabled_low_and_invalid_decisions_clean_without_promotion(self):
        dirty_html = (
            '<p><a href="https://fuente.example/articulo">Fuente normal</a></p>'
            '<section class="ammac-training-cta">Contenido falso '
            '<a href="https://attacker.example/offer">Oferta falsa</a></section>'
            '<p><a href="https://certificacionmontessori.com/inventado/">'
            "Certificaci\u00f3n no controlada</a></p>"
        )
        cases = (
            (False, resolve_conversion_decision("casa", "high", "post", "Post")),
            (True, resolve_conversion_decision("casa", "low", "post", "Post")),
            (True, resolve_conversion_decision("invented", "high", "post", "Post")),
        )

        for enabled, decision in cases:
            with self.subTest(enabled=enabled, decision=decision):
                with patch("config.CONVERSION_CTA_ENABLED", enabled):
                    output, stats = apply_conversion_funnel(dirty_html, decision)

                soup = BeautifulSoup(output, "html.parser")
                self.assertIsNotNone(
                    soup.find("a", href="https://fuente.example/articulo")
                )
                self.assertIsNone(
                    soup.find("a", href="https://attacker.example/offer")
                )
                self.assertIsNone(
                    soup.find(
                        "a",
                        href="https://certificacionmontessori.com/inventado/",
                    )
                )
                self.assertIn("Certificaci\u00f3n no controlada", soup.get_text())
                self.assertFalse(soup.select("[class*='ammac-training-']"))
                self.assertEqual(stats["cta_level"], "none")
                self.assertEqual(stats["contextual_links"], 0)
                self.assertEqual(stats["final_blocks"], 0)

    def test_disabled_hygiene_preserves_attribute_only_article_root(self):
        decision = resolve_conversion_decision("casa", "high", "post", "Post")
        html = (
            '<article id="editorial" data-program-id="invented" '
            'data-cta-position="final"><h2>Contenido editorial</h2>'
            '<p><a href="https://fuente.example/articulo">Fuente normal</a></p>'
            "</article>"
        )

        with patch("config.CONVERSION_CTA_ENABLED", False):
            output, stats = apply_conversion_funnel(html, decision)

        soup = BeautifulSoup(output, "html.parser")
        article = soup.find("article", id="editorial")
        self.assertIsNotNone(article)
        self.assertFalse(article.has_attr("data-program-id"))
        self.assertFalse(article.has_attr("data-cta-position"))
        self.assertEqual(article.h2.get_text(), "Contenido editorial")
        self.assertEqual(article.a["href"], "https://fuente.example/articulo")
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

    def test_strips_browser_normalized_backslash_commercial_links(self):
        commercial_urls = (
            "https://certificacionmontessori.com\\oferta",
            "https://www.certificacionmontessori.com\\oferta",
            "//certificacionmontessori.com\\oferta",
            "//www.certificacionmontessori.com\\oferta",
            "\\\\certificacionmontessori.com\\oferta",
            "\\\\www.certificacionmontessori.com\\oferta",
        )
        unrelated_urls = (
            "https://certificacionmontessori.com.evil.example\\oferta",
            "//certificacionmontessori.com.evil.example\\oferta",
        )
        html = "".join(
            f'<a href="{url}">Link {index}</a>'
            for index, url in enumerate((*commercial_urls, *unrelated_urls))
        )

        cleaned, removed = strip_uncontrolled_commercial_links(html)

        soup = BeautifulSoup(cleaned, "html.parser")
        self.assertEqual(removed, len(commercial_urls))
        self.assertEqual(
            [anchor["href"] for anchor in soup.find_all("a")],
            list(unrelated_urls),
        )

    def test_strips_whatwg_like_special_url_authorities(self):
        commercial_urls = (
            "https:////certificacionmontessori.com/oferta",
            "https:/\\/certificacionmontessori.com/oferta",
            "https:\\\\certificacionmontessori.com\\oferta",
            "http:certificacionmontessori.com/oferta",
            "////certificacionmontessori.com/oferta",
            "//www.certificacionmontessori.com/oferta",
            "\x00 \thttps:\r////certificacionmontessori.com/oferta\n ",
        )
        html = "".join(
            f'<a href="{url}">Comercial {index}</a>'
            for index, url in enumerate(commercial_urls)
        )

        cleaned, removed = strip_uncontrolled_commercial_links(html)

        soup = BeautifulSoup(cleaned, "html.parser")
        self.assertEqual(removed, len(commercial_urls))
        self.assertFalse(soup.find_all("a"))

    def test_strips_encoded_and_trailing_dot_certification_hosts_only(self):
        commercial_urls = (
            "https://%63ertificacionmontessori.com/oferta",
            "https://www.%63ertificacionmontessori.com./oferta",
        )
        unrelated_urls = (
            "https://certificacionmontessori.com.evil.example/oferta",
            "https://fuente.example/certificacionmontessori.com/oferta",
            "https://fuente.example/?next=certificacionmontessori.com",
        )
        html = "".join(
            f'<a href="{url}">Link {index}</a>'
            for index, url in enumerate((*commercial_urls, *unrelated_urls))
        )

        cleaned, removed = strip_uncontrolled_commercial_links(html)

        soup = BeautifulSoup(cleaned, "html.parser")
        self.assertEqual(removed, len(commercial_urls))
        self.assertEqual(
            [anchor["href"] for anchor in soup.find_all("a")],
            list(unrelated_urls),
        )

    def test_strips_one_trailing_root_dot_but_preserves_double_dot_host(self):
        single_dot_url = "https://certificacionmontessori.com./oferta"
        double_dot_url = "https://certificacionmontessori.com../oferta"
        html = (
            f'<a href="{single_dot_url}">Un punto</a>'
            f'<a href="{double_dot_url}">Dos puntos</a>'
        )

        cleaned, removed = strip_uncontrolled_commercial_links(html)

        soup = BeautifulSoup(cleaned, "html.parser")
        self.assertEqual(removed, 1)
        self.assertEqual([anchor["href"] for anchor in soup.find_all("a")], [double_dot_url])

    def test_preserves_unrelated_bracket_malformed_links(self):
        malformed_urls = (
            "https://[example.com/path",
            "https://example.com]/path",
        )
        html = "".join(
            f'<a href="{url}">Link {index}</a>'
            for index, url in enumerate(malformed_urls)
        )

        cleaned, removed = strip_uncontrolled_commercial_links(html)

        soup = BeautifulSoup(cleaned, "html.parser")
        self.assertEqual(removed, 0)
        self.assertEqual(
            [anchor["href"] for anchor in soup.find_all("a")],
            list(malformed_urls),
        )

    def test_strips_malformed_authority_conservatively(self):
        malformed_url = "https://[certificacionmontessori.com/oferta"
        html = f'<p><a href="{malformed_url}">Autoridad ambigua</a></p>'

        cleaned, removed = strip_uncontrolled_commercial_links(html)

        soup = BeautifulSoup(cleaned, "html.parser")
        self.assertEqual(removed, 1)
        self.assertIsNone(soup.a)
        self.assertIn("Autoridad ambigua", soup.get_text())

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
