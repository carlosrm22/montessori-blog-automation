import unittest

from unittest.mock import patch

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
        client.post.side_effect = RuntimeError("temporary failure")
        self.assertFalse(_post_json("https://hooks.example.test/event", {"ok": True}))
        self.assertEqual(client.post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)


if __name__ == "__main__":
    unittest.main()
