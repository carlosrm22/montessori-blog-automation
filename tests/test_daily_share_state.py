import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import state


class DailyShareStateTests(unittest.TestCase):
    def test_records_and_updates_daily_share_history(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            state.config, "DB_PATH", Path(tmp) / "state.db"
        ), patch.object(state.config, "DATA_DIR", Path(tmp)):
            self.assertEqual(state.get_daily_share_history(), {})
            state.mark_daily_share_sent(7, "https://example.test/7", "Título")
            self.assertIn(7, state.get_daily_share_history())
            state.mark_daily_share_sent(7, "https://example.test/7", "Título")
            self.assertIn(7, state.get_daily_share_history())


if __name__ == "__main__":
    unittest.main()
