import math
import unittest

from vrm1_to_vrm0 import mapping


class HumanBoneTest(unittest.TestCase):
    def test_thumb_is_shifted_one_step(self):
        self.assertEqual(mapping.vrm0_human_bone_name("right_thumb_metacarpal"), "rightThumbProximal")
        self.assertEqual(mapping.vrm0_human_bone_name("right_thumb_proximal"), "rightThumbIntermediate")
        self.assertEqual(mapping.vrm0_human_bone_name("left_thumb_distal"), "leftThumbDistal")

    def test_snake_to_camel(self):
        self.assertEqual(mapping.vrm0_human_bone_name("upper_chest"), "upperChest")
        self.assertEqual(mapping.vrm0_human_bone_name("hips"), "hips")
        self.assertEqual(mapping.vrm0_human_bone_name("left_index_intermediate"), "leftIndexIntermediate")


class ExpressionPresetTest(unittest.TestCase):
    def test_table(self):
        self.assertEqual(mapping.EXPRESSION_PRESETS["relaxed"], ("fun", "Fun"))
        self.assertEqual(mapping.EXPRESSION_PRESETS["happy"], ("joy", "Joy"))
        self.assertEqual(mapping.EXPRESSION_PRESETS["sad"], ("sorrow", "Sorrow"))
        self.assertEqual(mapping.EXPRESSION_PRESETS["blink_left"], ("blink_l", "Blink_L"))
        self.assertEqual(mapping.EXPRESSION_PRESETS["look_up"], ("lookup", "LookUp"))
        self.assertEqual(mapping.EXPRESSION_PRESETS["aa"], ("a", "A"))
        self.assertEqual(mapping.EXPRESSION_PRESETS["surprised"], ("unknown", "Surprised"))
        self.assertEqual(len(mapping.EXPRESSION_PRESETS), 18)

    def test_unique_name(self):
        used = {"Surprised"}
        self.assertEqual(mapping.unique_name("Surprised", used), "Surprised_2")
        self.assertEqual(mapping.unique_name("Surprised", used), "Surprised_3")
        self.assertEqual(mapping.unique_name("Joy", used), "Joy")
        self.assertIn("Joy", used)


class MaterialTest(unittest.TestCase):
    def test_color_property(self):
        self.assertEqual(mapping.MATERIAL_COLOR_PROPERTY["color"], "_Color")
        self.assertEqual(mapping.MATERIAL_COLOR_PROPERTY["emissionColor"], "_EmissionColor")
        self.assertIsNone(mapping.MATERIAL_COLOR_PROPERTY["matcapColor"])

    def test_main_tex_st(self):
        self.assertEqual(mapping.texture_transform_to_main_tex_st((2, 2), (0, 0)), [2, 2, 0, -1])
        st = mapping.texture_transform_to_main_tex_st((2, 2), (0.1, 0.2))
        self.assertAlmostEqual(st[3], -1.2)
        # Add-on の VRM0 → VRM1 の式（1 - offset_v - scale_v）で元に戻る
        self.assertAlmostEqual(1 - st[3] - st[1], 0.2)

    def test_linear_to_srgb_matches_addon(self):
        self.assertAlmostEqual(mapping.linear_to_srgb(0.5), math.pow(0.5, 1 / 2.2))
        self.assertEqual(mapping.linear_to_srgb(0.0), 0.0)


class LookAtFirstPersonTest(unittest.TestCase):
    def test_look_at(self):
        self.assertEqual(mapping.look_at_type("bone"), "Bone")
        self.assertEqual(mapping.look_at_type("expression"), "BlendShape")
        self.assertEqual(
            mapping.look_at_range(90.0, 10.0),
            {"curve": [0, 0, 0, 1, 1, 1, 1, 0], "x_range": 90.0, "y_range": 10.0},
        )

    def test_first_person_flag(self):
        self.assertEqual(mapping.first_person_flag("thirdPersonOnly"), "ThirdPersonOnly")
        self.assertEqual(mapping.first_person_flag("auto"), "Auto")


class CapsuleTest(unittest.TestCase):
    def test_capsule_spheres(self):
        spheres = mapping.capsule_spheres((0, 0, 0), (0, 0, 1), 0.25)
        self.assertEqual(len(spheres), 5)
        self.assertEqual(tuple(spheres[0]), (0, 0, 0))
        self.assertEqual(tuple(spheres[-1]), (0, 0, 1))

    def test_spacing_not_over_radius(self):
        spheres = mapping.capsule_spheres((0, 0, 0), (0.3, 0, 0), 0.07)
        for a, b in zip(spheres, spheres[1:]):
            self.assertLessEqual(math.dist(a, b), 0.07 + 1e-9)

    def test_degenerate_capsule(self):
        self.assertEqual(len(mapping.capsule_spheres((1, 2, 3), (1, 2, 3), 0.1)), 1)


SAMPLE_META = {
    "vrm_name": "サンプル アバター",
    "version": "1.0",
    "authors": ["Sample Author"],
    "copyright_information": "",
    "contact_information": "",
    "references": [],
    "third_party_licenses": "",
    "avatar_permission": "onlyAuthor",
    "allow_excessively_violent_usage": False,
    "allow_excessively_sexual_usage": False,
    "commercial_usage": "personalNonProfit",
    "allow_political_or_religious_usage": False,
    "allow_antisocial_or_hate_usage": False,
    "credit_notation": "required",
    "allow_redistribution": False,
    "modification": "prohibited",
    "other_license_url": "",
}


class MetaTest(unittest.TestCase):
    def test_restrictive_meta(self):
        meta0, items = mapping.meta_to_vrm0(SAMPLE_META)
        self.assertEqual(meta0["title"], "サンプル アバター")
        self.assertEqual(meta0["author"], "Sample Author")
        self.assertEqual(meta0["allowed_user_name"], "OnlyAuthor")
        self.assertEqual(meta0["commercial_ussage_name"], "Disallow")
        self.assertEqual(meta0["violent_ussage_name"], "Disallow")
        self.assertEqual(meta0["sexual_ussage_name"], "Disallow")
        self.assertEqual(meta0["license_name"], "Other")
        self.assertEqual(meta0["other_license_url"], "https://vrm.dev/licenses/1.0/")
        decisions = {i.target for i in items if i.kind == "needs_decision"}
        for key in ("credit_notation", "modification", "allow_redistribution"):
            self.assertIn(key, decisions)
        self.assertFalse([i for i in items if i.kind == "lossy"])

    def test_joined_authors_and_references(self):
        meta = dict(SAMPLE_META, authors=["A", "B"], references=["x", "y"])
        meta0, _ = mapping.meta_to_vrm0(meta)
        self.assertEqual(meta0["author"], "A, B")
        self.assertEqual(meta0["reference"], "x, y")

    def test_commercial_profit_is_lossy(self):
        meta0, items = mapping.meta_to_vrm0(dict(SAMPLE_META, commercial_usage="corporation"))
        self.assertEqual(meta0["commercial_ussage_name"], "Allow")
        self.assertEqual(len([i for i in items if i.kind == "lossy"]), 1)


class AxisTest(unittest.TestCase):
    def test_blender_world_vector_to_vrm0_storage(self):
        # 重力の向きも視線の位置も、Blender ワールドのベクトルを同じ式で VRM0 の欄に入れる
        self.assertEqual(mapping.vrm0_gravity_dir((1.0, 2.0, 3.0)), (-1.0, -2.0, 3.0))
        self.assertEqual(mapping.vrm0_first_person_offset((1.0, 2.0, 3.0)), (-1.0, -2.0, 3.0))


class ConfirmedAxisTest(unittest.TestCase):
    """VRM0 の JSON は Unity の座標（左手系、正面 +Z、キャラクターの左 -X）。
    Add-on は VRM0 の gravity_dir を JSON (x, z, y) として持つ。three-vrm 往復テストで確定。"""

    @staticmethod
    def vrm0_json(blender_value):
        x, y, z = blender_value
        return (x, z, y)

    def test_front(self):
        # VRM1 glTF 前 (0,0,1) → Add-on の Blender 値 (0,-1,0)
        self.assertEqual(self.vrm0_json(mapping.vrm0_gravity_dir((0.0, -1.0, 0.0))), (0.0, 0.0, 1.0))

    def test_down(self):
        self.assertEqual(self.vrm0_json(mapping.vrm0_gravity_dir((0.0, 0.0, -1.0))), (-0.0, -1.0, 0.0))

    def test_left(self):
        # VRM1 glTF 左 (1,0,0) → Unity の左は -X
        self.assertEqual(self.vrm0_json(mapping.vrm0_gravity_dir((1.0, 0.0, 0.0))), (-1.0, 0.0, -0.0))


if __name__ == "__main__":
    unittest.main()
