"""VRM0 用コライダー Empty の生成と掃除。触るのは VRM0_Colliders 内の VRM0_COL_ だけ。"""
import statistics

import bpy
from mathutils import Matrix

COLLECTION = "VRM0_Colliders"
PREFIX = "VRM0_COL_"


def _collection(scene):
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(COLLECTION)
    if coll.name not in scene.collection.children:
        scene.collection.children.link(coll)
    return coll


def clear_generated(context_scene, armature_obj):
    """VRM0_Colliders 内の VRM0_COL_ で始まり、このアーマチュアに付いたオブジェクトだけ消し、数を返す。

    ほかのアバターのために作ったものは消さない。
    """
    coll = bpy.data.collections.get(COLLECTION)
    if coll is None:
        return 0
    targets = [o for o in coll.objects if o.name.startswith(PREFIX) and o.parent == armature_obj]
    for obj in targets:
        bpy.data.objects.remove(obj, do_unlink=True)
    return len(targets)


def make_sphere(armature_obj, bone_name, world_pos, world_radius, name):
    """骨を親にした球表示の Empty を、ワールド位置・半径を合わせて作る。"""
    obj = bpy.data.objects.new(PREFIX + name, None)
    obj.empty_display_type = "SPHERE"
    _collection(bpy.context.scene).objects.link(obj)
    obj.parent = armature_obj
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    pose_bone = armature_obj.pose.bones[bone_name]
    # 骨を親にしたオブジェクトは、骨の先端（tail）を原点にした骨の行列に付く
    parent_matrix = (
        armature_obj.matrix_world
        @ pose_bone.matrix
        @ Matrix.Translation((0.0, pose_bone.bone.length, 0.0))
    )
    obj.matrix_parent_inverse = Matrix.Identity(4)
    obj.matrix_basis = parent_matrix.inverted() @ Matrix.Translation(world_pos)
    world_scale = statistics.mean(abs(s) for s in (parent_matrix @ obj.matrix_basis).to_scale())
    obj.empty_display_size = world_radius / world_scale if world_scale > 0 else world_radius
    return obj
