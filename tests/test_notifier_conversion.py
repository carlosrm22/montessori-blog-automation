import unittest

from unittest.mock import patch

import notifier
from notifier import _build_message, _post_json


class NotifierConversionTests(unittest.TestCase):
    def test_message_includes_controlled_decision(self):
        message = _build_message(
            post_id=42,
            title="Observación Montessori",
            topic_name="Casa de Niños",
            author_name="Roxana Muñoz",
            edit_url="https://montessorimexico.org/wp-admin/post.php?post=42&action=edit",
            truseo_score=82,
            headline_score=76,
            conversion_intent="casa",
            commercial_relevance="medium",
            destination_url="https://certificacionmontessori.com/diplomados/casa-de-ninos/",
        )
        self.assertIn("Conversión: casa / medium", message)
        self.assertIn(
            "Destino: https://certificacionmontessori.com/diplomados/casa-de-ninos/",
            message,
        )
        self.assertNotIn("TELEGRAM_BOT_TOKEN", message)

    @patch("notifier.time.sleep")
    @patch("notifier.httpx.Client")
    def test_http_notification_retries_three_times(self, client_class, sleep):
        client = client_class.return_value.__enter__.return_value
        client.post.side_effect = RuntimeError("secret-value-at-private-url")
        with self.assertLogs("notifier", level="WARNING") as logs:
            self.assertFalse(
                _post_json(
                    "https://secret.example.test/private-hook", {"ok": True}
                )
            )
        self.assertEqual(client.post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        rendered_logs = "\n".join(logs.output)
        self.assertIn("RuntimeError", rendered_logs)
        self.assertNotIn("secret-value", rendered_logs)
        self.assertNotIn("secret.example.test", rendered_logs)

    @patch("notifier._post_json", return_value=False)
    def test_configured_but_exhausted_channel_is_delivery_failure(self, post_json):
        with patch.multiple(
            notifier.config,
            NOTIFICATIONS_ENABLED=True,
            NOTIFY_WEBHOOK_URL="https://hooks.example.test/draft",
            TELEGRAM_BOT_TOKEN="",
            TELEGRAM_CHAT_ID="",
        ):
            with self.assertLogs("notifier", level="WARNING") as logs:
                notifier.notify_draft_created(
                    post_id=42,
                    title="Observación Montessori",
                    topic_name="Casa de Niños",
                    author_name="Roxana Muñoz",
                    edit_url="https://montessorimexico.org/wp-admin/post.php?post=42",
                )

        post_json.assert_called_once()
        rendered_logs = "\n".join(logs.output).lower()
        self.assertIn("falló", rendered_logs)
        self.assertIn("canales configurados", rendered_logs)
        self.assertNotIn("no hay canal", rendered_logs)


if __name__ == "__main__":
    unittest.main()
