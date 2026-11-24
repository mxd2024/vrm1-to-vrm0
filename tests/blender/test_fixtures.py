import os
import unittest

from tests.blender import fixtures
from tests.blender.helpers import FIXTURE_DIR, read_glb_json


class FixtureTest(unittest.TestCase):
    def build(self, kind):
        path = os.path.join(FIXTURE_DIR, f"{kind}.vrm")
        if os.path.exists(path):
            os.remove(path)
        self.assertEqual(fixtures.make_fixture(kind, path), path)
        self.assertTrue(os.path.exists(path))
        return read_glb_json(path)

    def test_basic(self):
        data = self.build("basic")
        self.assertIn("VRMC_vrm", data["extensions"])
        expressions = data["extensions"]["VRMC_vrm"]["expressions"]
        self.assertIn("happy", expressions["preset"])
        self.assertIn("Surprised", expressions["custom"])
        self.assertIn("Broken", expressions["custom"])

    def test_springs(self):
        data = self.build("springs")
        self.assertIn("VRMC_vrm", data["extensions"])
        spring = data["extensions"]["VRMC_springBone"]
        self.assertEqual(len(spring["springs"]), 5)
        shapes = sorted(next(iter(c["shape"])) for c in spring["colliders"])
        self.assertEqual(shapes, ["capsule", "sphere"])
        self.assertEqual(len(spring["colliderGroups"]), 2)

    def test_empty(self):
        data = self.build("empty")
        self.assertIn("VRMC_vrm", data["extensions"])
        self.assertNotIn("VRMC_springBone", data["extensions"])
