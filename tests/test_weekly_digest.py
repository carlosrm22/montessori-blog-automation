import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import weekly_digest


class WeeklyDigestTests(unittest.TestCase):
    def test_week_window_starts_monday_in_mexico_city(self):
        now = datetime(2026, 9, 4, 17, 0, tzinfo=ZoneInfo("America/Mexico_City"))
        start, end = weekly_digest.week_window(now, "America/Mexico_City")
        self.assertEqual(start.isoformat(), "2026-08-31T00:00:00-06:00")
        self.assertEqual(end, now)

    def test_builds_light_whatsapp_ready_message(self):
        start = datetime(2026, 8, 31, tzinfo=ZoneInfo("America/Mexico_City"))
        end = datetime(2026, 9, 4, 17, tzinfo=ZoneInfo("America/Mexico_City"))
        message, period = weekly_digest.build_whatsapp_digest(
            [
                {
                    "title": "Aprender *con* libertad",
                    "description": "<p>Una descripción breve para familias.</p>",
                    "url": "https://montessorimexico.org/aprender/",
                }
            ],
            start,
            end,
            160,
        )
        self.assertEqual(period, "31 de agosto al 4 de septiembre de 2026")
        self.assertIn("📚 *Publicaciones de la semana*", message)
        self.assertIn("1. *Aprender con libertad*", message)
        self.assertIn("Una descripción breve para familias.", message)
        self.assertIn("🔗 https://montessorimexico.org/aprender/", message)

    def test_long_description_is_shortened(self):
        value = "palabra " * 40
        result = weekly_digest._truncate(value, 80)
        self.assertLessEqual(len(result), 80)
        self.assertTrue(result.endswith("…"))

    def test_empty_week_has_short_message(self):
        now = datetime(2026, 9, 4, 17, tzinfo=ZoneInfo("America/Mexico_City"))
        start, end = weekly_digest.week_window(now, "America/Mexico_City")
        message, _ = weekly_digest.build_whatsapp_digest([], start, end, 160)
        self.assertIn("Esta semana no hubo publicaciones nuevas.", message)
        self.assertNotIn("🔗", message)

    @patch("weekly_digest.notify_weekly_digest", return_value=True)
    @patch("weekly_digest.list_published_posts_between")
    def test_run_queries_wordpress_in_utc_and_sends(self, list_posts, notify):
        list_posts.return_value = []
        now = datetime(2026, 9, 4, 17, tzinfo=ZoneInfo("America/Mexico_City"))
        with patch.multiple(
            weekly_digest.config,
            WEEKLY_DIGEST_TIMEZONE="America/Mexico_City",
            WEEKLY_DIGEST_DESCRIPTION_MAX_LEN=160,
        ):
            self.assertTrue(weekly_digest.run(now=now))
        list_posts.assert_called_once_with(
            after="2026-08-31T06:00:00Z", before="2026-09-04T23:00:00Z"
        )
        notify.assert_called_once()

    @patch("weekly_digest.notify_weekly_digest")
    @patch("weekly_digest.list_published_posts_between", return_value=[])
    def test_dry_run_does_not_send(self, list_posts, notify):
        now = datetime(2026, 9, 4, 17, tzinfo=ZoneInfo("America/Mexico_City"))
        with patch.multiple(
            weekly_digest.config,
            WEEKLY_DIGEST_TIMEZONE="America/Mexico_City",
            WEEKLY_DIGEST_DESCRIPTION_MAX_LEN=160,
        ), patch("builtins.print"):
            self.assertTrue(weekly_digest.run(dry_run=True, now=now))
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
