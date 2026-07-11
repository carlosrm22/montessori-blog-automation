import logging
import sys
import unittest

import httpx

from logging_security import RedactingFormatter, redact_text


class LoggingSecurityTests(unittest.TestCase):
    def test_redacts_telegram_token_inside_url(self):
        raw = "POST https://api.telegram.org/bot123456:ABC_secret/sendMessage"
        clean = redact_text(raw)
        self.assertNotIn("123456:ABC_secret", clean)
        self.assertIn("bot[REDACTED]/sendMessage", clean)

    def test_redacts_named_secret_assignment(self):
        clean = redact_text(
            "WP_APP_PASSWORD=abcd efgh ijkl mnop qrst uvwx\nstatus=failed"
        )
        self.assertEqual(clean, "WP_APP_PASSWORD=[REDACTED]\nstatus=failed")

    def test_formatter_redacts_exception_text(self):
        formatter = RedactingFormatter("%(levelname)s %(message)s")
        try:
            raise RuntimeError(
                "https://api.telegram.org/bot999999:XYZ/sendMessage failed"
            )
        except RuntimeError:
            record = logging.LogRecord(
                "test", logging.ERROR, __file__, 1, "notification failed", (),
                exc_info=__import__("sys").exc_info(),
            )
        rendered = formatter.format(record)
        self.assertNotIn("999999:XYZ", rendered)
        self.assertIn("[REDACTED]", rendered)

    def test_formatter_redacts_cse_key_in_http_status_error_url(self):
        formatter = RedactingFormatter("%(levelname)s %(message)s")
        request = httpx.Request(
            "GET",
            (
                "https://www.googleapis.com/customsearch/v1"
                "?key=dummy-cse-secret&cx=public-context&q=montessori"
            ),
        )
        response = httpx.Response(403, request=request)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            record = logging.LogRecord(
                "test",
                logging.ERROR,
                __file__,
                1,
                "Google CSE failed: %s",
                (exc,),
                exc_info=sys.exc_info(),
            )

        rendered = formatter.format(record)

        self.assertNotIn("dummy-cse-secret", rendered)
        self.assertIn("cx=public-context", rendered)
        self.assertIn("q=montessori", rendered)
        self.assertIn("key=[REDACTED]", rendered)

        ampersand_clean = redact_text(
            "https://www.googleapis.com/customsearch/v1"
            "?cx=public-context&key=second-dummy-secret&q=montessori"
        )
        self.assertNotIn("second-dummy-secret", ampersand_clean)
        self.assertIn("cx=public-context", ampersand_clean)
        self.assertIn("q=montessori", ampersand_clean)


if __name__ == "__main__":
    unittest.main()
