import unittest

from tests.blender.helpers import HAS_SAMPLE, SAMPLE_SKIP_REASON, SAMPLE_VRM, fixture_path, items, load_vrm, true_eye_position, vrm0_eye_position
from vrm1_to_vrm0 import mapping
from vrm1_to_vrm0.convert import convert_armature


def assigned_vrm0_bones(ext):
    return {b.bone: b.node.bone_name for b in ext.vrm0.humanoid.human_bones if b.node.bone_name}


@unittest.skipUnless(HAS_SAMPLE, SAMPLE_SKIP_REASON)
class SampleModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arm = load_vrm(SAMPLE_VRM)
        cls.ext = cls.arm.data.vrm_addon_extension
        cls.report = convert_armature(cls.arm)

    def test_humanoid(self):
        bones = assigned_vrm0_bones(self.ext)
        self.assertEqual(len(bones), 52)
        hb1 = self.ext.vrm1.humanoid.human_bones
        self.assertEqual(bones["leftThumbProximal"], hb1.left_thumb_metacarpal.node.bone_name)
        self.assertEqual(bones["leftThumbIntermediate"], hb1.left_thumb_proximal.node.bone_name)
        self.assertEqual(bones["hips"], hb1.hips.node.bone_name)

    def test_meta(self):
        meta0 = self.ext.vrm0.meta
        self.assertEqual(meta0.title, self.ext.vrm1.meta.vrm_name)
        self.assertEqual(meta0.author, ", ".join(a.value for a in self.ext.vrm1.meta.authors))
        self.assertTrue(meta0.author)
        self.assertEqual(meta0.license_name, "Other")
        self.assertEqual(meta0.other_license_url, "https://vrm.dev/licenses/1.0/")
        targets = {i.target for i in items(self.report, "meta", "needs_decision")}
        self.assertIn("credit_notation", targets)

    def test_look_at(self):
        fp = self.ext.vrm0.first_person
        self.assertEqual(fp.look_at_type_name, "BlendShape")
        self.assertEqual(fp.look_at_horizontal_inner.y_range, 10)
        self.assertEqual(fp.look_at_horizontal_inner.x_range, 90)
        self.assertEqual(list(fp.look_at_horizontal_inner.curve), [0, 0, 0, 1, 1, 1, 1, 0])
        self.assertGreaterEqual(len(items(self.report, "look_at", "needs_decision")), 1)

    def test_first_person(self):
        fp = self.ext.vrm0.first_person
        self.assertEqual(fp.first_person_bone.bone_name, self.ext.vrm1.humanoid.human_bones.head.node.bone_name)
        # 頭ノードが回転しているモデル。offsetFromHeadBone は頭ノードの向きで読む
        error = (vrm0_eye_position(self.arm) - true_eye_position(SAMPLE_VRM)).length
        self.assertLess(error, 1e-4)

    def test_summary_counts(self):
        self.assertEqual(self.report.summary["vrm1"]["human_bones"], 52)
        self.assertEqual(self.report.summary["vrm0"]["human_bones"], 52)
        self.assertEqual(self.report.summary["addon_version"], "4.4.0")

    def test_spec_version_unchanged(self):
        self.assertEqual(self.ext.spec_version, "1.0")

    def test_second_run_is_same(self):
        convert_armature(self.arm)
        self.assertEqual(len(assigned_vrm0_bones(self.ext)), 52)
        self.assertEqual(len(self.ext.vrm0.humanoid.human_bones), len({b.bone for b in self.ext.vrm0.humanoid.human_bones}))


class BasicFixtureTest(unittest.TestCase):
    def test_first_person_offset_and_annotation(self):
        arm = load_vrm(fixture_path("basic"))
        ext = arm.data.vrm_addon_extension
        convert_armature(arm)
        fp = ext.vrm0.first_person
        error = (vrm0_eye_position(arm) - true_eye_position(fixture_path("basic"))).length
        self.assertLess(error, 1e-4)
        annotations = [(a.mesh.mesh_object_name, a.first_person_flag) for a in fp.mesh_annotations]
        self.assertEqual(annotations, [("Face", "ThirdPersonOnly")])


class EmptyFixtureTest(unittest.TestCase):
    def test_empty_model_converts(self):
        arm = load_vrm(fixture_path("empty"))
        report = convert_armature(arm)
        self.assertTrue(items(report, "first_person", "info"))
