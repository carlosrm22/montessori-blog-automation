import unittest
from unittest.mock import patch

import config
from quality_gate import check_title_novelty


class QualityGateTests(unittest.TestCase):
    def test_rejects_near_duplicate_title(self):
        result = check_title_novelty(
            "Constructivismo y aprendizaje activo para familias",
            ["Constructivismo y Aprendizaje Activo: claves para familias"],
            0.82,
        )
        self.assertFalse(result.accepted)
        self.assertGreaterEqual(result.highest_similarity, 0.82)

    def test_accepts_distinct_title(self):
        result = check_title_novelty(
            "El silencio como preparación del ambiente",
            ["Matemáticas Montessori: pensar con las manos"],
            0.82,
        )
        self.assertTrue(result.accepted)

    def test_normalizes_accents_case_and_punctuation(self):
        result = check_title_novelty(
            "Observación: el niño y la guía",
            ["observacion del nino y la guia"],
            0.82,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(
            result.matched_title, "observacion del nino y la guia"
        )

    def test_empty_history_is_accepted_without_a_match(self):
        result = check_title_novelty("Nuevo título", [], 0.82)
        self.assertTrue(result.accepted)
        self.assertEqual(result.highest_similarity, 0.0)
        self.assertEqual(result.matched_title, "")

    def test_non_empty_zero_score_history_matches_first_title(self):
        result = check_title_novelty("abc", ["xyz", "uvw"], 0.82)
        self.assertTrue(result.accepted)
        self.assertEqual(result.highest_similarity, 0.0)
        self.assertEqual(result.matched_title, "xyz")

    def test_validate_rejects_recent_posts_count_outside_bounds(self):
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
            SITE_TITLE="Asociación Montessori de México",
            TITLE_SEPARATOR="|",
            BRAND_KIT="ammac",
            QUALITY_RECENT_POSTS_COUNT=0,
            TITLE_SIMILARITY_MAX=0.82,
        ):
            with self.assertRaises(SystemExit):
                config.validate()

    def test_validate_rejects_similarity_threshold_outside_bounds(self):
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
            SITE_TITLE="Asociación Montessori de México",
            TITLE_SEPARATOR="|",
            BRAND_KIT="ammac",
            QUALITY_RECENT_POSTS_COUNT=30,
            TITLE_SIMILARITY_MAX=1.0,
        ):
            with self.assertRaises(SystemExit):
                config.validate()

    def test_validate_rejects_non_finite_similarity_thresholds(self):
        for threshold in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(threshold=threshold):
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
                    SITE_TITLE="Asociación Montessori de México",
                    TITLE_SEPARATOR="|",
                    BRAND_KIT="ammac",
                    QUALITY_RECENT_POSTS_COUNT=30,
                    TITLE_SIMILARITY_MAX=threshold,
                ):
                    with self.assertRaises(SystemExit):
                        config.validate()


if __name__ == "__main__":
    unittest.main()
