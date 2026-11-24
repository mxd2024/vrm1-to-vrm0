import unittest

from vrm1_to_vrm0 import addon_check


class SmokeTest(unittest.TestCase):
    def test_vrm_addon_version_is_found(self):
        self.assertEqual(addon_check.find_vrm_addon_version(), (4, 4, 0))
