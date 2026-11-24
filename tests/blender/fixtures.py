"""テスト用の小さな VRM1 モデルを作って書き出す。"""
import os

import bpy
from mathutils import Vector


def _enum_key(prop_owner, prop_name, word):
    keys = prop_owner.bl_rna.properties[prop_name].enum_items.keys()
    return next(k for k in keys if word in k.lower())


def _base(title):
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.icyp.make_basic_armature()
    arm = bpy.context.active_object
    ext = arm.data.vrm_addon_extension
    ext.spec_version = "1.0"
    meta = ext.vrm1.meta
    meta.vrm_name = title
    meta.authors.add().value = "vrm1-to-vrm0 tests"
    return arm


def _add_mesh(arm):
    """head に追従する小さなメッシュ（シェイプキー Smile / WinkL、MToon 材質）。"""
    head = arm.data.bones["head"]
    center = arm.matrix_world @ head.head_local + Vector((0, 0, 0.1))
    bpy.ops.mesh.primitive_cube_add(size=0.1, location=center)
    mesh = bpy.context.active_object
    mesh.name = "Face"
    group = mesh.vertex_groups.new(name="head")
    group.add([v.index for v in mesh.data.vertices], 1.0, "REPLACE")
    mesh.parent = arm
    mesh.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = mesh.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    mesh.shape_key_add(name="Basis")
    for name, dz in (("Smile", 0.01), ("WinkL", -0.01)):
        key = mesh.shape_key_add(name=name)
        for point in key.data:
            point.co.z += dz
    mat = bpy.data.materials.new("FaceMat")
    mat.vrm_addon_extension.mtoon1.enabled = True
    mesh.data.materials.append(mat)
    bpy.context.view_layer.objects.active = arm
    return mesh, mat


def _custom(ext, name):
    expr = ext.vrm1.expressions.custom.add()
    expr.custom_name = name
    return expr


def _bind_morph(expr, mesh, key, weight):
    bind = expr.morph_target_binds.add()
    bind.node.mesh_object_name = mesh.name
    bind.index = key
    bind.weight = weight


def _build_basic():
    arm = _base("basic fixture")
    ext = arm.data.vrm_addon_extension
    mesh, mat = _add_mesh(arm)
    preset = ext.vrm1.expressions.preset
    _bind_morph(preset.happy, mesh, "Smile", 1.0)
    preset.happy.override_blink = "block"
    surprised = _custom(ext, "Surprised")
    _bind_morph(surprised, mesh, "WinkL", 0.5)
    color = preset.aa.material_color_binds.add()
    color.material = mat
    color.type = "color"
    color.target_value = (1.0, 0.0, 0.0, 1.0)
    transform = preset.aa.texture_transform_binds.add()
    transform.material = mat
    transform.scale = (2.0, 2.0)
    transform.offset = (0.1, 0.2)
    broken = _custom(ext, "Broken")
    _bind_morph(broken, mesh, "NoSuchKey", 1.0)
    look_at = ext.vrm1.look_at
    look_at.type = "expression"
    look_at.offset_from_head_bone = (0.0, 0.06, 0.02)
    annotation = ext.vrm1.first_person.mesh_annotations.add()
    annotation.node.mesh_object_name = mesh.name
    annotation.type = "thirdPersonOnly"
    return arm


def _add_chain(arm, prefix, direction, count=3, length=0.04, offset=(0.0, 0.0, 0.0)):
    """head の子として prefix1..N のチェーンを作り、骨名を返す。"""
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode="EDIT")
    bones = arm.data.edit_bones
    parent = bones["head"]
    start = parent.head + Vector((0, 0, 0.12)) + Vector(offset)
    names = []
    for i in range(count):
        bone = bones.new(f"{prefix}{i + 1}")
        bone.head = start + Vector(direction) * length * i
        bone.tail = start + Vector(direction) * length * (i + 1)
        bone.parent = parent
        bone.use_connect = i > 0
        parent = bone
        names.append(bone.name)
    bpy.ops.object.mode_set(mode="OBJECT")
    return names


def _add_spring(sb, name, bones, gravity_dir=(0.0, 0.0, -1.0), stiffness=(0.0, 0.0, 0.0), groups=()):
    spring = sb.springs.add()
    spring.vrm_name = name
    for bone, stiff in zip(bones, stiffness):
        joint = spring.joints.add()
        joint.node.bone_name = bone
        joint.stiffness = stiff
        joint.gravity_power = 1.0
        joint.gravity_dir = gravity_dir
        joint.drag_force = 0.4
        joint.hit_radius = 0.02
    for group in groups:
        spring.collider_groups.add().collider_group_uuid = group.uuid
    return spring


def _add_collider(arm, bone, kind, offset, radius, tail=None):
    sb = arm.data.vrm_addon_extension.spring_bone1
    bpy.ops.vrm.add_spring_bone1_collider(armature_object_name=arm.name)
    collider = sb.colliders[-1]
    collider.node.bone_name = bone
    collider.shape_type = _enum_key(collider, "shape_type", kind)
    collider.reset_bpy_object(bpy.context, arm)
    shape = getattr(collider.shape, kind)
    shape.offset = offset
    shape.radius = radius
    if tail is not None:
        shape.tail = tail
    return collider


def _add_group(arm, name, colliders):
    sb = arm.data.vrm_addon_extension.spring_bone1
    bpy.ops.vrm.add_spring_bone1_collider_group(armature_object_name=arm.name)
    group = sb.collider_groups[-1]
    group.vrm_name = name
    for collider in colliders:
        group.colliders.add().collider_uuid = collider.uuid
    return group


# 重力の向き（VRM1 の glTF 値）→ Add-on が Blender 上で持つ値 (x, -z, y)
GRAVITY_GLTF = {"Front": (0.0, 0.0, 1.0), "Left": (1.0, 0.0, 0.0), "Down": (0.0, -1.0, 0.0)}


def gltf_to_blender_dir(v):
    x, y, z = v
    return (x, -z, y)


def _build_springs():
    arm = _base("springs fixture")
    sb = arm.data.vrm_addon_extension.spring_bone1
    chains = {
        "Front": _add_chain(arm, "Front", (0, -1, 0)),
        "Left": _add_chain(arm, "Left", (1, 0, 0)),
        # 静止時にコライダーへ食い込まない位置に置く（食い込むと押し出し方が実装ごとに違い、比較にならない）
        "Down": _add_chain(arm, "Down", (0, 0, -1), offset=(0.08, 0.0, 0.0)),
        "Var": _add_chain(arm, "Var", (-1, 0, 0)),
    }
    sphere = _add_collider(arm, "head", "sphere", (0.0, 0.0, 0.05), 0.05)
    capsule = _add_collider(arm, "head", "capsule", (0.0, 0.0, 0.0), 0.03, tail=(0.0, 0.1, 0.0))
    g_sphere = _add_group(arm, "HeadSphere", [sphere])
    g_capsule = _add_group(arm, "HeadCapsule", [capsule])
    for name in ("Front", "Left", "Down"):
        _add_spring(
            sb, name, chains[name], gravity_dir=gltf_to_blender_dir(GRAVITY_GLTF[name]),
            groups=(g_sphere, g_capsule),
        )
    _add_spring(sb, "Var", chains["Var"], stiffness=(1.0, 2.0, 3.0), groups=(g_sphere,))
    _add_spring(sb, "Nested", chains["Var"][1:], stiffness=(0.5, 0.5))
    return arm


def _build_empty():
    return _base("empty fixture")


BUILDERS = {"basic": _build_basic, "springs": _build_springs, "empty": _build_empty}


def make_fixture(kind, out_path):
    """kind の VRM1 モデルを作り out_path に書き出し、読み直して VRM1 であることを確かめる。"""
    arm = BUILDERS[kind]()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    result = bpy.ops.export_scene.vrm(
        filepath=out_path, armature_object_name=arm.name, ignore_warning=True
    )
    if result != {"FINISHED"}:
        raise RuntimeError(f"export failed: {result}")
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.vrm(filepath=out_path)
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if len(armatures) != 1 or armatures[0].data.vrm_addon_extension.spec_version != "1.0":
        raise RuntimeError(f"fixture {kind} did not read back as VRM1")
    return out_path
