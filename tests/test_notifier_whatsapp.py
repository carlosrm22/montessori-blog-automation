import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import notifier


class WhatsAppNotifierTests(unittest.TestCase):
    @patch("notifier.subprocess.run")
    def test_resolves_single_allowlisted_target(self, run):
        run.return_value = SimpleNamespace(
            returncode=0, stdout=json.dumps(["521234567890"]), stderr=""
        )
        with patch.multiple(
            notifier.config,
            OPENCLAW_CLI="openclaw",
            OPENCLAW_WHATSAPP_TARGET="",
        ):
            self.assertEqual(notifier._resolve_whatsapp_target(), "521234567890")

    @patch("notifier.subprocess.run")
    def test_multiple_allowlisted_targets_require_explicit_choice(self, run):
        run.return_value = SimpleNamespace(
            returncode=0,
            stdout=json.dumps(["521234567890", "521234567891"]),
            stderr="",
        )
        with patch.multiple(
            notifier.config,
            OPENCLAW_CLI="openclaw",
            OPENCLAW_WHATSAPP_TARGET="",
        ):
            self.assertEqual(notifier._resolve_whatsapp_target(), "")

    @patch("notifier.subprocess.run")
    @patch("notifier._resolve_whatsapp_target", return_value="521234567890")
    def test_sends_message_and_media_without_logging_payload(self, resolve, run):
        run.return_value = SimpleNamespace(returncode=0, stdout="{}", stderr="")
        with patch.object(notifier.config, "OPENCLAW_CLI", "openclaw"):
            self.assertTrue(
                notifier._send_whatsapp(
                    "mensaje privado", "https://example.test/cover.jpg"
                )
            )
        command = run.call_args.args[0]
        self.assertIn("whatsapp", command)
        self.assertIn("--media", command)
        self.assertIn("https://example.test/cover.jpg", command)

    @patch("notifier._send_whatsapp", return_value=True)
    def test_weekly_digest_is_delivered_by_whatsapp(self, send):
        with patch.multiple(
            notifier.config,
            NOTIFICATIONS_ENABLED=True,
            NOTIFY_WEBHOOK_URL="",
        ):
            self.assertTrue(
                notifier.notify_weekly_digest(
                    message="resumen",
                    posts=[],
                    period_label="semana",
                )
            )
        send.assert_called_once_with("resumen")


if __name__ == "__main__":
    unittest.main()
