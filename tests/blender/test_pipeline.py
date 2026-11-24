import os
import shutil
import unittest

from tests.blender.helpers import HAS_SAMPLE, OUT, SAMPLE_SKIP_REASON, SAMPLE_VRM, read_glb_json
from vrm1_to_vrm0 import pipeline

JP_DIR = os.path.join(OUT, "日本語 フォルダ")
SAMPLE_OUT = os.path.join(JP_DIR, "sample_vrm0.vrm")


@unittest.skipUnless(HAS_SAMPLE, SAMPLE_SKIP_REASON)
class SampleModelPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shutil.rmtree(JP_DIR, ignore_errors=True)
        stat = os.stat(SAMPLE_VRM)
        cls.source_before = (stat.st_mtime_ns, stat.st_size)
        cls.code, cls.report, cls.json_path = pipeline.convert_file(SAMPLE_VRM, SAMPLE_OUT, overwrite=False)

    def test_success(self):
        self.assertEqual(self.code, 0)
        self.assertEqual(self.json_path, SAMPLE_OUT + ".report.json")
        self.assertTrue(os.path.exists(self.json_path))
        self.assertTrue(os.path.exists(SAMPLE_OUT + ".report.md"))

    def test_output_is_vrm0(self):
        data = read_glb_json(SAMPLE_OUT)
        self.assertIn("VRM", data["extensions"])
        self.assertNotIn("VRMC_vrm", data.get("extensions", {}))
        self.assertNotIn("VRMC_vrm", data.get("extensionsUsed", []))

    def test_roundtrip_counts(self):
        roundtrip = self.report.summary["roundtrip"]
        self.assertEqual(roundtrip["human_bones"], {"expected": 52, "actual": 52, "match": True})
        self.assertEqual(roundtrip["blend_shape_groups"]["actual"], 36)
        self.assertEqual(roundtrip["bone_groups"]["actual"], 19)
        for key, value in roundtrip.items():
            self.assertTrue(value["match"], key)

    def test_source_untouched(self):
        stat = os.stat(SAMPLE_VRM)
        self.assertEqual((stat.st_mtime_ns, stat.st_size), self.source_before)

    def test_existing_output_is_not_overwritten(self):
        before = os.stat(SAMPLE_OUT).st_mtime_ns
        code, _report, json_path = pipeline.convert_file(SAMPLE_VRM, SAMPLE_OUT, overwrite=False)
        self.assertEqual(code, 1)
        self.assertIsNone(json_path)
        self.assertEqual(os.stat(SAMPLE_OUT).st_mtime_ns, before)

    def test_vrm0_input_is_rejected(self):
        code, report, _ = pipeline.convert_file(SAMPLE_OUT, os.path.join(JP_DIR, "again.vrm"), overwrite=True)
        self.assertEqual(code, 2)
        self.assertIn("VRM0", report.items[-1].message)
        self.assertFalse(os.path.exists(os.path.join(JP_DIR, "again.vrm")))


class PreconditionTest(unittest.TestCase):
    def test_missing_input(self):
        code, report, json_path = pipeline.convert_file(os.path.join(OUT, "nope.vrm"), None, overwrite=False)
        self.assertEqual(code, 2)
        self.assertIsNone(json_path)

    def test_default_output_path(self):
        self.assertEqual(
            pipeline.default_output_path(r"C:\a b\モデル.vrm"),
            r"C:\a b\モデル_vrm0.vrm",
        )
