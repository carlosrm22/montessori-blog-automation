import unittest

from content import (
    COMMERCIAL_RELEVANCE_LEVELS,
    CONVERSION_INTENTS,
    _normalize_generated_post,
)


def generated_payload(**overrides):
    payload = {
        "title": "Observación en Casa de Niños",
        "body": "<h2>Observación Montessori</h2><p>" + "palabra " * 700 + "</p>",
        "excerpt": "Cómo observar y acompañar el ambiente Montessori.",
        "categories": ["Educación Montessori"],
        "tags": ["observación", "Montessori"],
        "seo_title": "Observación en Casa de Niños",
        "seo_description": "Observación en Casa de Niños para acompañar el aprendizaje.",
        "focus_keyphrase": "observación Montessori",
        "og_title": "Observación en Casa de Niños",
        "og_description": "Una mirada práctica a la observación Montessori.",
        "twitter_title": "Observación en Casa de Niños",
        "twitter_description": "Una mirada práctica a la observación Montessori.",
        "social_image_source": "featured_media",
        "image_prompt": "Editorial Montessori classroom photograph",
        "image_alt_text": "Guía observando un ambiente Montessori",
        "conversion_intent": "casa",
        "commercial_relevance": "medium",
    }
    payload.update(overrides)
    return payload


class ContentConversionContractTests(unittest.TestCase):
    def test_preserves_valid_enum_values(self):
        post = _normalize_generated_post(generated_payload())
        self.assertEqual(post.conversion_intent, "casa")
        self.assertEqual(post.commercial_relevance, "medium")

    def test_invalid_values_fall_back_to_no_promotion(self):
        post = _normalize_generated_post(
            generated_payload(
                conversion_intent="https://invented.example/program",
                commercial_relevance="urgent",
            )
        )
        self.assertEqual(post.conversion_intent, "editorial")
        self.assertEqual(post.commercial_relevance, "low")

    def test_every_declared_enum_value_normalizes_without_expansion(self):
        for intent in CONVERSION_INTENTS:
            relevance = "low" if intent == "editorial" else "medium"
            with self.subTest(intent=intent):
                post = _normalize_generated_post(
                    generated_payload(
                        conversion_intent=intent,
                        commercial_relevance=relevance,
                    )
                )
                self.assertEqual(post.conversion_intent, intent)
                self.assertEqual(post.commercial_relevance, relevance)
        for relevance in COMMERCIAL_RELEVANCE_LEVELS:
            with self.subTest(relevance=relevance):
                post = _normalize_generated_post(
                    generated_payload(commercial_relevance=relevance)
                )
                self.assertEqual(post.commercial_relevance, relevance)


if __name__ == "__main__":
    unittest.main()
