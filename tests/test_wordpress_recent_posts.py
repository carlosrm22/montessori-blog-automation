import unittest
from unittest.mock import Mock, patch

import httpx

import wordpress


class WordPressRecentPostsTests(unittest.TestCase):
    def _valid_row(self, **overrides):
        row = {
            "id": 7,
            "link": "https://wordpress.example.test/post",
            "title": {"rendered": "Valid title"},
        }
        row.update(overrides)
        return row

    def _assert_malformed_row_raises(self, row):
        response = Mock()
        response.json.return_value = [row]
        with patch.object(wordpress, "_request", return_value=response):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_recent_published_posts(limit=12)

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

    def test_successful_empty_list_is_preserved(self):
        response = Mock()
        response.json.return_value = []
        with patch.object(wordpress, "_request", return_value=response):
            self.assertEqual(wordpress.list_recent_published_posts(limit=12), [])

    def test_non_dict_row_raises_history_unavailable(self):
        self._assert_malformed_row_raises("not-a-post")

    def test_invalid_ids_raise_history_unavailable(self):
        invalid_ids = (None, 0, -1, 1.5, "7", True)
        for invalid_id in invalid_ids:
            with self.subTest(post_id=invalid_id):
                self._assert_malformed_row_raises(self._valid_row(id=invalid_id))

    def test_missing_id_raises_history_unavailable(self):
        row = self._valid_row()
        del row["id"]
        self._assert_malformed_row_raises(row)

    def test_invalid_rendered_titles_raise_history_unavailable(self):
        invalid_titles = (
            None,
            {},
            {"rendered": None},
            {"rendered": ""},
            {"rendered": "   "},
            {"rendered": 123},
        )
        for title in invalid_titles:
            with self.subTest(title=title):
                self._assert_malformed_row_raises(self._valid_row(title=title))

    def test_missing_title_raises_history_unavailable(self):
        row = self._valid_row()
        del row["title"]
        self._assert_malformed_row_raises(row)

    def test_invalid_links_raise_history_unavailable(self):
        invalid_links = (None, "", "   ", 123)
        for link in invalid_links:
            with self.subTest(link=link):
                self._assert_malformed_row_raises(self._valid_row(link=link))

    def test_missing_link_raises_history_unavailable(self):
        row = self._valid_row()
        del row["link"]
        self._assert_malformed_row_raises(row)

    def test_any_unusable_row_rejects_an_otherwise_valid_response(self):
        response = Mock()
        response.json.return_value = [self._valid_row(), self._valid_row(id=0)]
        with patch.object(wordpress, "_request", return_value=response):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_recent_published_posts(limit=12)

    def test_unusable_row_after_requested_limit_still_rejects_response(self):
        response = Mock()
        response.json.return_value = [self._valid_row(), self._valid_row(id=0)]
        with patch.object(wordpress, "_request", return_value=response):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_recent_published_posts(limit=1)

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
