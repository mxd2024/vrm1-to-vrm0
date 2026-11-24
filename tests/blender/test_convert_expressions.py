import unittest

from tests.blender.helpers import HAS_SAMPLE, SAMPLE_SKIP_REASON, SAMPLE_VRM, fixture_path, items, load_vrm
from vrm1_to_vrm0.convert import convert_armature


def groups_by_name(ext):
    return {g.name: g for g in ext.vrm0.blend_shape_master.blend_shape_groups}


def material_values(group):
    return {mv.property_name: [v.value for v in mv.target_value] for mv in group.material_values}


@unittest.skipUnless(HAS_SAMPLE, SAMPLE_SKIP_REASON)
class SampleModelExpressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arm = load_vrm(SAMPLE_VRM)
        cls.ext = cls.arm.data.vrm_addon_extension
        cls.report = convert_armature(cls.arm)

    def test_group_count(self):
        self.assertEqual(len(self.ext.vrm0.blend_shape_master.blend_shape_groups), 36)
        self.assertEqual(self.report.summary["vrm0"]["blend_shape_groups"], 36)

    def test_joy_binds_follow_happy(self):
        joy = [g for g in self.ext.vrm0.blend_shape_master.blend_shape_groups if g.preset_name == "joy"]
        self.assertEqual(len(joy), 1)
        happy = self.ext.vrm1.expressions.preset.happy
        self.assertEqual(len(joy[0].binds), len(happy.morph_target_binds))
        self.assertEqual(len(joy[0].binds), 3)
        first = happy.morph_target_binds[0]
        self.assertEqual(joy[0].binds[0].mesh.mesh_object_name, first.node.mesh_object_name)
        self.assertEqual(joy[0].binds[0].index, first.index)
        self.assertAlmostEqual(joy[0].binds[0].weight, first.weight)

    def test_surprised_is_unknown(self):
        self.assertEqual(groups_by_name(self.ext)["Surprised"].preset_name, "unknown")

    def test_override_losses(self):
        self.assertEqual(len(items(self.report, "expressions", "lossy")), 18)

    def test_second_run_is_same(self):
        convert_armature(self.arm)
        self.assertEqual(len(self.ext.vrm0.blend_shape_master.blend_shape_groups), 36)


class BasicExpressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arm = load_vrm(fixture_path("basic"))
        cls.ext = cls.arm.data.vrm_addon_extension
        broken = next(e for e in cls.ext.vrm1.expressions.custom if e.custom_name == "Broken")
        bind = broken.morph_target_binds.add()  # 書き出し時に落ちるので、読み込み後に足す
        bind.node.mesh_object_name = "Face"
        bind.index = "NoSuchKey"
        bind.weight = 1.0
        cls.report = convert_armature(cls.arm)

    def test_material_values(self):
        values = material_values(groups_by_name(self.ext)["A"])
        self.assertEqual(set(values), {"_Color", "_MainTex_ST"})
        for a, b in zip(values["_MainTex_ST"], [2, 2, 0.1, -1.2]):
            self.assertAlmostEqual(a, b, places=5)
        for a, b in zip(values["_Color"], [1, 0, 0, 1]):
            self.assertAlmostEqual(a, b, places=5)

    def test_broken_bind_is_skipped(self):
        self.assertEqual(len(groups_by_name(self.ext)["Broken"].binds), 0)
        lossy = [i for i in items(self.report, "expressions", "lossy") if i.target == "Broken"]
        self.assertEqual(len(lossy), 1)

    def test_name_collision(self):
        groups = groups_by_name(self.ext)
        self.assertEqual(groups["Surprised"].preset_name, "unknown")
        self.assertEqual(len(groups["Surprised_2"].binds), 1)
        self.assertTrue([i for i in items(self.report, "expressions", "info") if i.target == "Surprised_2"])

    def test_override_blink_reported(self):
        lossy = [i for i in items(self.report, "expressions", "lossy") if i.target == "Joy"]
        self.assertEqual(len(lossy), 1)
