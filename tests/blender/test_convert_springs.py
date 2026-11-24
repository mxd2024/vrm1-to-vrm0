import unittest

import bpy

from tests.blender.helpers import HAS_SAMPLE, SAMPLE_SKIP_REASON, SAMPLE_VRM, fixture_path, items, load_vrm
from vrm1_to_vrm0 import colliders, mapping
from vrm1_to_vrm0.convert import convert_armature


def bone_groups(ext):
    return {g.comment: g for g in ext.vrm0.secondary_animation.bone_groups}


def collider_group_by_uuid(ext):
    return {g.uuid: g for g in ext.vrm0.secondary_animation.collider_groups}


def generated_empties():
    return [o for o in bpy.data.objects if o.name.startswith(colliders.PREFIX)]


@unittest.skipUnless(HAS_SAMPLE, SAMPLE_SKIP_REASON)
class SampleModelSpringTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arm = load_vrm(SAMPLE_VRM)
        cls.ext = cls.arm.data.vrm_addon_extension
        cls.report = convert_armature(cls.arm)

    def test_bone_group_per_spring(self):
        self.assertEqual(len(self.ext.vrm0.secondary_animation.bone_groups), 19)
        self.assertEqual(self.report.summary["vrm0"]["bone_groups"], 19)

    def test_values_copied_one_to_one(self):
        groups = bone_groups(self.ext)
        for spring in self.ext.spring_bone1.springs:
            root = spring.joints[0]
            group = groups[spring.vrm_name]
            self.assertAlmostEqual(group.stiffiness, root.stiffness, places=5)
            self.assertAlmostEqual(group.gravity_power, root.gravity_power, places=5)
            self.assertAlmostEqual(group.drag_force, root.drag_force, places=5)
            self.assertAlmostEqual(group.hit_radius, root.hit_radius, places=5)
            for a, b in zip(group.gravity_dir, mapping.vrm0_gravity_dir(tuple(root.gravity_dir))):
                self.assertAlmostEqual(a, b, places=5)
            self.assertEqual([b.bone_name for b in group.bones], [root.node.bone_name])
        stiffness = {round(g.stiffiness, 3) for g in groups.values()}
        self.assertEqual(stiffness, {6.0, 5.0, 2.5})  # 髪・スカート・イヤリング

    def test_collider_groups_keep_lineage(self):
        self.assertGreaterEqual(len(self.ext.vrm0.secondary_animation.collider_groups), 10)
        lineage = self.report.summary["collider_group_map"]
        groups = bone_groups(self.ext)
        for spring in self.ext.spring_bone1.springs:
            expected = set()
            for ref in spring.collider_groups:
                expected.update(lineage[ref.collider_group_uuid])
            actual = {ref.collider_group_uuid for ref in groups[spring.vrm_name].collider_groups}
            self.assertEqual(actual, expected, spring.vrm_name)

    def test_each_vrm0_group_is_one_bone_of_one_vrm1_group(self):
        lineage = self.report.summary["collider_group_map"]
        owners = {}
        for v1, v0_list in lineage.items():
            for v0 in v0_list:
                self.assertNotIn(v0, owners)
                owners[v0] = v1
        for group in self.ext.vrm0.secondary_animation.collider_groups:
            for collider in group.colliders:
                self.assertEqual(collider.bpy_object.parent_bone, group.node.bone_name)


class SpringsFixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.arm = load_vrm(fixture_path("springs"))
        cls.ext = cls.arm.data.vrm_addon_extension
        user = bpy.data.objects.new("UserEmpty", None)
        bpy.context.scene.collection.objects.link(user)
        cls.report = convert_armature(cls.arm)

    def test_nested_spring_is_skipped(self):
        groups = bone_groups(self.ext)
        self.assertEqual(sorted(groups), ["Down", "Front", "Left", "Var"])
        self.assertTrue([i for i in items(self.report, "spring", "lossy") if i.target == "Nested"])

    def test_uneven_joint_values_use_root(self):
        self.assertAlmostEqual(bone_groups(self.ext)["Var"].stiffiness, 1.0, places=5)
        self.assertTrue([i for i in items(self.report, "spring", "lossy") if i.target == "Var"])

    def test_gravity_direction(self):
        groups = bone_groups(self.ext)
        springs = {s.vrm_name: s for s in self.ext.spring_bone1.springs}
        for name in ("Front", "Left", "Down"):
            expected = mapping.vrm0_gravity_dir(tuple(springs[name].joints[0].gravity_dir))
            for a, b in zip(groups[name].gravity_dir, expected):
                self.assertAlmostEqual(a, b, places=5)

    def test_lateral_gravity_needs_decision(self):
        flagged = {i.target for i in items(self.report, "spring", "needs_decision")}
        self.assertEqual(flagged, {"Left"})

    def test_sphere_and_capsule_stay_in_separate_groups(self):
        front = bone_groups(self.ext)["Front"]
        by_uuid = collider_group_by_uuid(self.ext)
        referenced = [by_uuid[r.collider_group_uuid] for r in front.collider_groups]
        self.assertEqual(len(referenced), 2)
        self.assertEqual({g.node.bone_name for g in referenced}, {"head"})
        counts = sorted(len(g.colliders) for g in referenced)
        capsule = next(c for c in self.ext.spring_bone1.colliders if c.shape_type.lower() == "capsule")
        head = capsule.bpy_object.matrix_world.to_translation()
        tail = capsule.bpy_object.children[0].matrix_world.to_translation()
        expected = len(mapping.capsule_spheres(tuple(head), tuple(tail), capsule.shape.capsule.radius))
        self.assertEqual(counts, sorted([1, expected]))
        self.assertTrue(items(self.report, "colliders", "info"))

    def test_sphere_position_and_radius(self):
        sphere = next(c for c in self.ext.spring_bone1.colliders if c.shape_type.lower() == "sphere")
        bpy.context.view_layer.update()
        one = [o for o in generated_empties() if "HeadSphere" in o.name]
        self.assertEqual(len(one), 1)
        world = one[0].matrix_world
        self.assertLess((world.to_translation() - sphere.bpy_object.matrix_world.to_translation()).length, 1e-5)
        mean_scale = sum(abs(s) for s in world.to_scale()) / 3
        self.assertAlmostEqual(one[0].empty_display_size * mean_scale, sphere.shape.sphere.radius, places=5)
        self.assertIn(one[0].name, bpy.data.collections[colliders.COLLECTION].objects)

    def test_second_run_logs_no_addon_errors(self):
        with self.assertNoLogs(level="ERROR"):
            convert_armature(self.arm)

    def test_second_run_is_same_and_keeps_user_objects(self):
        before = len(generated_empties())
        convert_armature(self.arm)
        self.assertEqual(len(generated_empties()), before)
        self.assertIn("UserEmpty", bpy.data.objects)
        self.assertEqual(len(self.ext.vrm0.secondary_animation.bone_groups), 4)


class TwoAvatarsTest(unittest.TestCase):
    def test_second_avatar_keeps_first_avatars_colliders(self):
        first = load_vrm(fixture_path("springs"))
        convert_armature(first)
        first_empties = {o.name for o in generated_empties() if o.parent == first}
        self.assertTrue(first_empties)
        bpy.ops.import_scene.vrm(filepath=fixture_path("springs"))
        second = next(o for o in bpy.data.objects if o.type == "ARMATURE" and o != first)
        convert_armature(second)
        self.assertTrue(first_empties <= {o.name for o in generated_empties()})
        self.assertTrue([o for o in generated_empties() if o.parent == second])
        for group in first.data.vrm_addon_extension.vrm0.secondary_animation.collider_groups:
            for collider in group.colliders:
                self.assertIsNotNone(collider.bpy_object)


class EmptyFixtureSpringTest(unittest.TestCase):
    def test_no_springs(self):
        arm = load_vrm(fixture_path("empty"))
        report = convert_armature(arm)
        self.assertEqual(len(items(report, "spring", "info")), 1)
        self.assertEqual(len(arm.data.vrm_addon_extension.vrm0.secondary_animation.bone_groups), 0)
