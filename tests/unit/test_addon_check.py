import unittest

from vrm1_to_vrm0 import addon_check


class EvaluateTest(unittest.TestCase):
    def test_tested_version_is_ok(self):
        self.assertEqual(addon_check.evaluate((4, 4, 0))[0], "ok")

    def test_newer_version_warns(self):
        self.assertEqual(addon_check.evaluate((4, 5, 0))[0], "warn")

    def test_older_version_warns(self):
        self.assertEqual(addon_check.evaluate((3, 20, 0))[0], "warn")

    def test_missing_addon(self):
        status, message = addon_check.evaluate(None)
        self.assertEqual(status, "missing")
        self.assertTrue(message)


if __name__ == "__main__":
    unittest.main()
