import os
import shutil
import time
import unittest

import bpy

import vrm1_to_vrm0
from tests.blender.helpers import HAS_SAMPLE, OUT, SAMPLE_SKIP_REASON, SAMPLE_VRM, fixture_path, load_vrm
from vrm1_to_vrm0 import ops

OUT_DIR = os.path.join(OUT, "ops 日本語")


INSTALLED = "bl_ext.user_default.vrm1_to_vrm0"


class OpsTest(unittest.TestCase):
    """作業フォルダの版を登録して試す。導入済みの版は一時的に外し、終わったら戻す（設定は保存しない）。"""

    @classmethod
    def setUpClass(cls):
        import addon_utils

        cls.installed = INSTALLED in bpy.context.preferences.addons
        if cls.installed:
            addon_utils.disable(INSTALLED, default_set=False)
        vrm1_to_vrm0.register()

    @classmethod
    def tearDownClass(cls):
        import addon_utils

        vrm1_to_vrm0.unregister()
        if cls.installed:
            addon_utils.enable(INSTALLED, default_set=False)

    def test_copy_to_vrm0(self):
        arm = load_vrm(fixture_path("basic"))
        bpy.context.view_layer.objects.active = arm
        result = bpy.ops.vrm1_to_vrm0.copy_to_vrm0()
        self.assertEqual(result, {"FINISHED"})
        self.assertIn(ops.REPORT_TEXT, bpy.data.texts)
        self.assertIn("要判断", bpy.data.texts[ops.REPORT_TEXT].as_string())
        self.assertEqual(arm.data.vrm_addon_extension.spec_version, "1.0")
        self.assertGreater(len(arm.data.vrm_addon_extension.vrm0.blend_shape_master.blend_shape_groups), 0)

    def test_copy_is_unavailable_for_vrm0_model(self):
        arm = load_vrm(fixture_path("basic"))
        ext = arm.data.vrm_addon_extension
        ext.spec_version = "0.0"
        ext.vrm0.blend_shape_master.blend_shape_groups.add().name = "HandMade"
        bpy.context.view_layer.objects.active = arm
        with self.assertRaises(RuntimeError):
            bpy.ops.vrm1_to_vrm0.copy_to_vrm0()
        names = [g.name for g in ext.vrm0.blend_shape_master.blend_shape_groups]
        self.assertEqual(names, ["HandMade"])

    def test_cancel_clears_running_flag(self):
        from types import SimpleNamespace

        wm = bpy.context.window_manager
        wm.vrm1_to_vrm0.running = True
        ops.VRM1TO0_OT_convert_file.cancel(SimpleNamespace(_timer=None, _job=None), bpy.context)
        self.assertFalse(wm.vrm1_to_vrm0.running)

    @unittest.skipUnless(HAS_SAMPLE, SAMPLE_SKIP_REASON)
    def test_convert_file_in_separate_process(self):
        load_vrm(fixture_path("basic"))  # 開いているファイルの代わり
        before = (len(bpy.data.objects), len(bpy.data.images), len(bpy.data.materials))
        shutil.rmtree(OUT_DIR, ignore_errors=True)
        out = os.path.join(OUT_DIR, "サンプル_vrm0.vrm")
        job = ops.start_conversion(SAMPLE_VRM, out, overwrite=False)
        deadline = time.time() + 600
        result = None
        while result is None and time.time() < deadline:
            time.sleep(0.5)
            result = ops.poll_conversion(job)
        self.assertIsNotNone(result)
        code, report_path, _lines = result
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(out))
        self.assertEqual(os.path.normcase(report_path), os.path.normcase(out + ".report.json"))
        after = (len(bpy.data.objects), len(bpy.data.images), len(bpy.data.materials))
        self.assertEqual(before, after)


class RetryTest(unittest.TestCase):
    def test_retry_only_after_a_crash(self):
        self.assertFalse(ops.needs_retry(0, attempts=1))
        self.assertFalse(ops.needs_retry(1, attempts=1))
        self.assertFalse(ops.needs_retry(2, attempts=1))
        self.assertTrue(ops.needs_retry(3221225477, attempts=1))  # 0xC0000005（ほかのアドオンによる起動時の異常終了）
        self.assertFalse(ops.needs_retry(3221225477, attempts=2))
