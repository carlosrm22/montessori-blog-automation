import unittest
from unittest.mock import Mock, patch

import httpx

import wordpress


class WordPressRecentPostsTests(unittest.TestCase):
    @patch("wordpress.httpx.Client")
    def test_requested_limit_above_thirty_is_sent_as_per_page(self, client_class):
        response = httpx.Response(
            200,
            json=[],
            request=httpx.Request("GET", "https://wordpress.example.test/posts"),
        )
        client = client_class.return_value.__enter__.return_value
        client.get.return_value = response

        with patch.multiple(
            wordpress.config,
            WP_SITE_URL="https://wordpress.example.test",
            WP_USERNAME="test-user",
            WP_APP_PASSWORD="test-password",
        ):
            posts = wordpress.list_recent_published_posts(limit=75)

        self.assertEqual(posts, [])
        self.assertEqual(client.get.call_args.kwargs["params"]["per_page"], 75)

    def test_request_failure_raises_history_unavailable(self):
        with patch.object(wordpress, "_request", return_value=None):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_recent_published_posts(limit=12)

    def test_json_parse_failure_raises_history_unavailable(self):
        response = Mock()
        response.json.side_effect = ValueError("private response body")

        with patch.object(wordpress, "_request", return_value=response):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_recent_published_posts(limit=12)

    def test_malformed_post_shape_raises_history_unavailable(self):
        response = Mock()
        response.json.return_value = [
            {
                "id": 7,
                "link": "https://wordpress.example.test/post",
                "title": "not-a-rendered-title-object",
            }
        ]

        with patch.object(wordpress, "_request", return_value=response):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_recent_published_posts(limit=12)

    @patch("wordpress.httpx.Client")
    def test_request_failure_log_omits_authenticated_url_and_exception_body(
        self, client_class
    ):
        client = client_class.return_value.__enter__.return_value
        client.get.side_effect = httpx.RequestError(
            "private exception body",
            request=httpx.Request(
                "GET", "https://wordpress.example.test/wp-json/wp/v2/posts"
            ),
        )

        with patch.multiple(
            wordpress.config,
            WP_SITE_URL="https://wordpress.example.test",
            WP_USERNAME="test-user",
            WP_APP_PASSWORD="test-password",
        ), self.assertLogs("wordpress", level="ERROR") as captured:
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_recent_published_posts(limit=12)

        rendered = "\n".join(captured.output)
        self.assertNotIn("https://wordpress.example.test", rendered)
        self.assertNotIn("private exception body", rendered)
        self.assertIn("RequestError", rendered)


if __name__ == "__main__":
    unittest.main()
