import unittest
from pathlib import Path

from unittest.mock import patch

import notifier
from notifier import _build_message, _post_json


class NotifierConversionTests(unittest.TestCase):
    @patch("notifier._send_telegram", return_value=True)
    @patch("notifier._send_webhook", return_value=False)
    def test_weekly_digest_uses_existing_channels(self, webhook, telegram):
        with patch.multiple(
            notifier.config,
            NOTIFICATIONS_ENABLED=True,
            NOTIFY_WEBHOOK_URL="",
            TELEGRAM_BOT_TOKEN="token",
            TELEGRAM_CHAT_ID="chat",
        ):
            sent = notifier.notify_weekly_digest(
                message="resumen",
                posts=[{"id": 7, "title": "Tema", "url": "https://example.test"}],
                period_label="1 al 5 de septiembre de 2026",
            )
        self.assertTrue(sent)
        telegram.assert_called_once_with("resumen")

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

    def test_manual_message_contains_exact_prompt_path_and_project_command(self):
        prompt = "PROMPT EXACTO\ncon segunda línea"
        with patch.object(notifier.config, "BASE_DIR", Path("/srv/montessori")):
            message = notifier._build_manual_image_message(
                job_id="img-20260722-120000-1234abcd",
                title="Observación Montessori",
                alt_text="Guía en un ambiente preparado",
                full_prompt=prompt,
                expected_path="/srv/montessori/data/manual_image_queue/inbox/job.png",
            )

        self.assertIn(prompt, message)
        self.assertIn("Texto alternativo: Guía en un ambiente preparado", message)
        self.assertIn(
            "/srv/montessori/process_manual_cover.sh img-20260722-120000-1234abcd",
            message,
        )

    @patch("notifier._post_json", return_value=True)
    def test_telegram_chunks_preserve_long_prompt_without_truncation(self, post_json):
        message = "inicio\n" + ("abc123" * 1500) + "\nfin"
        with patch.multiple(
            notifier.config,
            TELEGRAM_BOT_TOKEN="token",
            TELEGRAM_CHAT_ID="chat",
        ):
            self.assertTrue(notifier._send_telegram(message))

        chunks = [call.args[1]["text"] for call in post_json.call_args_list]
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 3900 for chunk in chunks))
        self.assertEqual("".join(chunks), message)


if __name__ == "__main__":
    unittest.main()
