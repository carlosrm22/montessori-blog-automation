import unittest
from unittest.mock import Mock, call, patch

import content
from search import SearchResult


class ContentResilienceTests(unittest.TestCase):
    def setUp(self):
        self.article = SearchResult(
            title="Educación inclusiva",
            url="https://example.com/inclusion",
            snippet="Estrategias actuales para acompañar a cada estudiante.",
        )

    def test_configures_bounded_sdk_request_without_internal_retries(self):
        client = Mock()
        client.models.generate_content.side_effect = RuntimeError("unavailable")

        with (
            patch.object(content.genai, "Client", return_value=client) as factory,
            patch.object(content.config, "GEMINI_CONTENT_TIMEOUT_SECONDS", 45.5),
            patch.object(content.config, "GEMINI_CONTENT_RETRY_DELAY_SECONDS", 0),
        ):
            result = content.generate_post(self.article, max_retries=1)

        self.assertIsNone(result)
        http_options = factory.call_args.kwargs["http_options"]
        self.assertEqual(http_options.timeout, 45500)
        self.assertEqual(http_options.retry_options.attempts, 1)

    def test_retries_with_exponential_delay(self):
        client = Mock()
        client.models.generate_content.side_effect = RuntimeError("busy")

        with (
            patch.object(content.genai, "Client", return_value=client),
            patch.object(content.config, "GEMINI_CONTENT_TIMEOUT_SECONDS", 120),
            patch.object(content.config, "GEMINI_CONTENT_MAX_ATTEMPTS", 3),
            patch.object(content.config, "GEMINI_CONTENT_RETRY_DELAY_SECONDS", 2),
            patch.object(content.time, "sleep") as sleep,
        ):
            result = content.generate_post(self.article)

        self.assertIsNone(result)
        self.assertEqual(client.models.generate_content.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(2), call(4)])


if __name__ == "__main__":
    unittest.main()
