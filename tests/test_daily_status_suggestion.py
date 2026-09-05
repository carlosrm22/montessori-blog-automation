import unittest
from unittest.mock import patch

import daily_status_suggestion as daily


class DailyStatusSuggestionTests(unittest.TestCase):
    def _post(self, post_id=7, title="Ambiente preparado"):
        return {
            "id": post_id,
            "title": title,
            "description": "Una reflexión práctica para acompañar a niñas y niños.",
            "url": f"https://montessorimexico.org/post-{post_id}/",
            "image_url": f"https://montessorimexico.org/cover-{post_id}.jpg",
        }

    def test_prefers_newest_never_sent_post(self):
        posts = [self._post(9), self._post(8)]
        self.assertEqual(daily.select_post(posts, {9: "2026-09-01"})["id"], 8)

    def test_cycles_to_least_recently_sent_post(self):
        posts = [self._post(9), self._post(8)]
        history = {9: "2026-09-03T00:00:00Z", 8: "2026-08-30T00:00:00Z"}
        self.assertEqual(daily.select_post(posts, history)["id"], 8)

    def test_message_contains_title_description_and_article_url(self):
        message = daily.build_status_message(self._post())
        self.assertNotIn("Lectura del día", message)
        self.assertTrue(
            message.startswith("https://montessorimexico.org/post-7/\n")
        )
        self.assertIn("*Ambiente preparado*", message)
        self.assertIn(
            "Una reflexión práctica para acompañar a niñas y niños.", message
        )
        self.assertIn("https://montessorimexico.org/post-7/", message)
        self.assertNotIn("Lee el artículo completo", message)
        self.assertNotIn("Listo para compartir", message)

    def test_description_is_limited_to_120_characters(self):
        description = daily._short_description("palabra " * 40)
        self.assertLessEqual(len(description), 120)
        self.assertTrue(description.endswith("…"))

    def test_message_uses_a_description_fallback_but_keeps_the_url(self):
        post = self._post()
        post["description"] = ""
        message = daily.build_status_message(post)
        self.assertIn("Una lectura para acompañar", message)
        self.assertIn(post["url"], message)

    @patch("daily_status_suggestion.state.mark_daily_share_sent")
    @patch("daily_status_suggestion.state.get_daily_share_history", return_value={})
    @patch("daily_status_suggestion.notify_daily_status_suggestion", return_value=True)
    @patch("daily_status_suggestion.list_recent_published_posts")
    def test_successful_delivery_is_recorded(self, list_posts, notify, history, mark):
        post = self._post()
        list_posts.return_value = [post]
        self.assertTrue(daily.run())
        notify.assert_called_once_with(
            message=daily.build_status_message(post),
            image_url=post["image_url"],
            post=post,
        )
        mark.assert_called_once_with(post["id"], post["url"], post["title"])

    @patch("daily_status_suggestion.state.mark_daily_share_sent")
    @patch("daily_status_suggestion.state.get_daily_share_history", return_value={})
    @patch("daily_status_suggestion.notify_daily_status_suggestion")
    @patch("daily_status_suggestion.list_recent_published_posts")
    def test_dry_run_neither_sends_nor_records(self, list_posts, notify, history, mark):
        list_posts.return_value = [self._post()]
        with patch("builtins.print"):
            self.assertTrue(daily.run(dry_run=True))
        notify.assert_not_called()
        mark.assert_not_called()


if __name__ == "__main__":
    unittest.main()
