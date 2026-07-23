import unittest

from image_gen import _is_zero_quota_error


class ImageQuotaTests(unittest.TestCase):
    def test_detects_permanent_zero_quota(self):
        error = RuntimeError(
            "429 RESOURCE_EXHAUSTED: quota exceeded, limit: 0, model: image"
        )
        self.assertTrue(_is_zero_quota_error(error))

    def test_does_not_treat_temporary_rate_limit_as_zero_quota(self):
        error = RuntimeError(
            "429 RESOURCE_EXHAUSTED: quota exceeded, limit: 15, retry in 30s"
        )
        self.assertFalse(_is_zero_quota_error(error))


if __name__ == "__main__":
    unittest.main()
