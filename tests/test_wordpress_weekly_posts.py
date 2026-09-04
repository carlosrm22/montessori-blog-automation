import unittest
from unittest.mock import Mock, patch

import wordpress


class WordPressWeeklyPostsTests(unittest.TestCase):
    def test_queries_published_interval_and_cleans_content(self):
        response = Mock()
        response.json.return_value = [
            {
                "id": 9,
                "link": "https://montessorimexico.org/post/",
                "title": {"rendered": "Título &amp; Montessori"},
                "excerpt": {"rendered": "<p>Descripción <strong>breve</strong>.</p>"},
                "date_gmt": "2026-09-03T15:00:00",
            }
        ]
        with patch.object(wordpress, "_request", return_value=response) as request:
            posts = wordpress.list_published_posts_between(
                "2026-08-31T06:00:00Z", "2026-09-04T23:00:00Z"
            )
        self.assertEqual(posts[0]["title"], "Título & Montessori")
        self.assertEqual(posts[0]["description"], "Descripción breve.")
        params = request.call_args.kwargs["params"]
        self.assertEqual(params["status"], "publish")
        self.assertEqual(params["order"], "asc")
        self.assertEqual(params["after"], "2026-08-31T06:00:00Z")
        self.assertEqual(params["before"], "2026-09-04T23:00:00Z")

    def test_unavailable_response_fails_closed(self):
        with patch.object(wordpress, "_request", return_value=None):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_published_posts_between("start", "end")

    def test_invalid_post_shape_fails_closed(self):
        response = Mock()
        response.json.return_value = [{"id": 0}]
        with patch.object(wordpress, "_request", return_value=response):
            with self.assertRaises(wordpress.RecentPostsUnavailable):
                wordpress.list_published_posts_between("start", "end")


if __name__ == "__main__":
    unittest.main()
