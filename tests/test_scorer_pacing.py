import unittest
from unittest.mock import patch

import scorer


class ScorerPacingTests(unittest.TestCase):
    def setUp(self):
        scorer._last_scorer_request_at = None

    def tearDown(self):
        scorer._last_scorer_request_at = None

    def test_waits_only_for_remaining_interval(self):
        with (
            patch.object(scorer.config, "SCORER_MIN_INTERVAL_SECONDS", 4.1),
            patch.object(
                scorer.time,
                "monotonic",
                side_effect=[100.0, 101.0],
            ),
            patch.object(scorer.time, "sleep") as sleep,
        ):
            scorer._pace_scorer_request()
            scorer._pace_scorer_request()

        sleep.assert_called_once()
        self.assertAlmostEqual(sleep.call_args.args[0], 3.1)
        self.assertAlmostEqual(scorer._last_scorer_request_at, 104.1)

    def test_zero_interval_disables_pacing(self):
        with (
            patch.object(scorer.config, "SCORER_MIN_INTERVAL_SECONDS", 0.0),
            patch.object(scorer.time, "sleep") as sleep,
            patch.object(scorer.time, "monotonic") as monotonic,
        ):
            scorer._pace_scorer_request()

        sleep.assert_not_called()
        monotonic.assert_not_called()


if __name__ == "__main__":
    unittest.main()
