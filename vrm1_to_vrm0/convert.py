"""VRM Add-on の VRM1 設定欄 → VRM0 設定欄の写し替え。VRM1 側は読むだけ。"""
import uuid

import bpy
from mathutils import Matrix, Vector

from . import addon_check, colliders, mapping
from .report import Report

LOOK_AT_DIRECTIONS = (
    ("range_map_horizontal_inner", "look_at_horizontal_inner"),
    ("range_map_horizontal_outer", "look_at_horizontal_outer"),
    ("range_map_vertical_down", "look_at_vertical_down"),
    ("range_map_vertical_up", "look_at_vertical_up"),
)

# VRMC_node_constraint は Blender の拘束として持たれている
NODE_CONSTRAINT_TYPES = {"COPY_ROTATION", "DAMPED_TRACK"}


def _vrm1_human_bones(ext):
    """(VRM1 の骨名, Blender の骨名) を割り当て済みのものだけ返す。"""
    human_bones = ext.vrm1.humanoid.human_bones
    result = []
    for prop in human_bones.bl_rna.properties:
        if prop.type != "POINTER":
            continue
        value = getattr(human_bones, prop.identifier)
        node = getattr(value, "node", None)
        if node is not None and node.bone_name:
            result.append((prop.identifier, node.bone_name))
    return result


def _convert_humanoid(ext, report):
    vrm0_bones = ext.vrm0.humanoid.human_bones
    vrm0_bones.clear()
    for vrm1_name, bone_name in _vrm1_human_bones(ext):
        vrm0_name = mapping.vrm0_human_bone_name(vrm1_name)
        entry = vrm0_bones.add()
        entry.bone = vrm0_name
        entry.node.bone_name = bone_name
    report.add(
        "humanoid", "info", "thumb",
        "親指は VRM1 の Metacarpal/Proximal/Distal を VRM0 の Proximal/Intermediate/Distal に割り当てました。",
    )


def _meta1_dict(meta1):
    data = {}
    for prop in meta1.bl_rna.properties:
        key = prop.identifier
        if key in ("rna_type", "name", "thumbnail_image") or key.startswith("active_"):
            continue
        value = getattr(meta1, key)
        if prop.type == "COLLECTION":
            value = [item.value for item in value]
        data[key] = value
    return data


def _convert_meta(ext, report):
    meta1 = ext.vrm1.meta
    meta0 = ext.vrm0.meta
    values, items = mapping.meta_to_vrm0(_meta1_dict(meta1))
    for key, value in values.items():
        setattr(meta0, key, value)
    meta0.other_permission_url = ""
    meta0.texture = meta1.thumbnail_image
    report.extend(items)


def _look_at_offset_world(armature_obj, ext):
    """VRM1 の offset_from_head_bone は頭の骨の向きでのベクトル。Blender ワールドの向きに直す。

    Add-on は読み込み時に骨の軸の付け替え（axis_translation）を逆にかけて持つので、ここで戻す。
    """
    head = armature_obj.data.bones.get(ext.vrm1.humanoid.human_bones.head.node.bone_name)
    offset = Vector(ext.vrm1.look_at.offset_from_head_bone)
    if head is None:
        return offset
    bone_ext = head.vrm_addon_extension
    axis = bone_ext.reverse_axis_translation(bone_ext.axis_translation)
    to_bone = bone_ext.translate_axis(Matrix(), axis).to_3x3()
    rotation = (armature_obj.matrix_world @ head.matrix_local).to_3x3().normalized()
    return rotation @ (to_bone @ offset)


def _convert_look_at_first_person(ext, armature_obj, report):
    look_at = ext.vrm1.look_at
    fp = ext.vrm0.first_person
    fp.look_at_type_name = mapping.look_at_type(look_at.type)
    odd = []
    for vrm1_attr, vrm0_attr in LOOK_AT_DIRECTIONS:
        range1 = getattr(look_at, vrm1_attr)
        values = mapping.look_at_range(range1.input_max_value, range1.output_scale)
        range0 = getattr(fp, vrm0_attr)
        range0.curve = values["curve"]
        range0.x_range = values["x_range"]
        range0.y_range = values["y_range"]
        if look_at.type == "expression" and range1.output_scale > 1.0:
            odd.append((vrm0_attr, range1.output_scale))
    if odd:
        report.add(
            "look_at", "needs_decision", "y_range",
            "視線が表情方式なのに出力の大きさ（y_range）が 1 を超えています。VRM0 の利用先では視線の表情が強く出すぎる可能性があります。そのまま写しました。",
            values={name: value for name, value in odd},
        )

    head = ext.vrm1.humanoid.human_bones.head.node.bone_name
    fp.first_person_bone.bone_name = head
    fp.first_person_bone_offset = mapping.vrm0_first_person_offset(
        tuple(_look_at_offset_world(armature_obj, ext))
    )

    fp.mesh_annotations.clear()
    annotations = ext.vrm1.first_person.mesh_annotations
    for annotation in annotations:
        entry = fp.mesh_annotations.add()
        entry.mesh.mesh_object_name = annotation.node.mesh_object_name
        entry.first_person_flag = mapping.first_person_flag(annotation.type)
    if not annotations:
        report.add("first_person", "info", "mesh_annotations", "一人称のメッシュ設定はありません。")


def _emissive_strength(material):
    return material.vrm_addon_extension.mtoon1.extensions.khr_materials_emissive_strength.emissive_strength


def _color_value(material, bind_type, value):
    """Add-on が材質の同じ項目を VRM0 へ書き出すときと同じ変換（linear → sRGB、発光は強さを掛ける）。"""
    rgb = [mapping.linear_to_srgb(max(c, 0.0)) for c in value[:3]]
    alpha = value[3] if len(value) > 3 else 1.0
    if bind_type == "emissionColor":
        strength = _emissive_strength(material)
        rgb = [c * strength for c in rgb]
    return [*rgb, alpha]


def _add_material_value(group, material, property_name, values):
    entry = group.material_values.add()
    entry.material = material
    entry.property_name = property_name
    for v in values:
        entry.target_value.add().value = v


def _shape_key_exists(mesh_object_name, key_name):
    obj = bpy.data.objects.get(mesh_object_name)
    if obj is None or obj.type != "MESH" or obj.data.shape_keys is None:
        return False
    return key_name in obj.data.shape_keys.key_blocks


def _copy_expression(expr, group, name, report):
    for bind in expr.morph_target_binds:
        mesh_name = bind.node.mesh_object_name
        if not _shape_key_exists(mesh_name, bind.index):
            report.add(
                "expressions", "lossy", name,
                f"バインド先のシェイプキーがないため飛ばしました（メッシュ {mesh_name!r}、シェイプキー {bind.index!r}）。",
                mesh=mesh_name, shape_key=bind.index,
            )
            continue
        entry = group.binds.add()
        entry.mesh.mesh_object_name = mesh_name
        entry.index = bind.index
        entry.weight = bind.weight
    for bind in expr.material_color_binds:
        property_name = mapping.MATERIAL_COLOR_PROPERTY.get(bind.type)
        if bind.material is None or property_name is None:
            reason = "材質がない" if bind.material is None else f"VRM0 に {bind.type} の対応がない"
            report.add(
                "expressions", "lossy", name,
                f"材質色のバインドを落としました（{reason}）。",
                type=bind.type, material=bind.material.name if bind.material else None,
            )
            continue
        values = _color_value(bind.material, bind.type, list(bind.target_value))
        _add_material_value(group, bind.material, property_name, values)
    for bind in expr.texture_transform_binds:
        if bind.material is None:
            report.add("expressions", "lossy", name, "テクスチャ位置のバインドを落としました（材質がない）。")
            continue
        values = mapping.texture_transform_to_main_tex_st(tuple(bind.scale), tuple(bind.offset))
        _add_material_value(group, bind.material, "_MainTex_ST", values)
    group.is_binary = expr.is_binary
    overrides = {
        key: getattr(expr, key)
        for key in ("override_blink", "override_look_at", "override_mouth")
        if getattr(expr, key) != "none"
    }
    if overrides:
        report.add(
            "expressions", "lossy", name,
            "VRM0 には抑制設定がないため、まばたき・視線・口の表情と重なる可能性があります。",
            **overrides,
        )


def _convert_expressions(ext, report):
    groups = ext.vrm0.blend_shape_master.blend_shape_groups
    groups.clear()
    expressions = ext.vrm1.expressions
    used = set()
    sources = [
        (getattr(expressions.preset, key), preset_name, name)
        for key, (preset_name, name) in mapping.EXPRESSION_PRESETS.items()
    ]
    sources += [(expr, "unknown", expr.custom_name) for expr in expressions.custom]
    for expr, preset_name, wanted in sources:
        name = mapping.unique_name(wanted, used)
        if name != wanted:
            report.add(
                "expressions", "info", name,
                f"名前 {wanted!r} が重なったため {name!r} にしました。",
            )
        group = groups.add()
        group.name = name
        group.preset_name = preset_name
        _copy_expression(expr, group, name, report)


JOINT_VALUES = ("stiffness", "gravity_power", "drag_force", "hit_radius")


def _collider_shapes(armature_obj, collider, report):
    """VRM1 コライダー → [(ワールド位置, 半径)]。表せないものは [] を返し report に書く。"""
    name = collider.bpy_object.name if collider.bpy_object else collider.uuid
    extended = collider.extensions.vrmc_spring_bone_extended_collider
    kind = collider.shape_type.lower()
    if extended.enabled:
        shape = getattr(collider.shape, kind, None)
        bone = armature_obj.pose.bones.get(collider.node.bone_name)
        if shape is None or bone is None or not hasattr(shape, "fallback_offset"):
            report.add("colliders", "lossy", name, "拡張コライダーは VRM0 で表せず、代わりの形もないため落としました。")
            return []
        base = armature_obj.matrix_world @ bone.matrix
        head = base @ Vector(shape.fallback_offset)
        tail = base @ Vector(shape.fallback_tail) if kind == "capsule" else None
        radius = shape.fallback_radius
        report.add("colliders", "lossy", name, "拡張コライダーは VRM0 で表せないため、代わりの形（fallback）を使いました。")
    else:
        if collider.bpy_object is None:
            report.add("colliders", "lossy", name, "コライダーのオブジェクトがないため落としました。")
            return []
        head = collider.bpy_object.matrix_world.to_translation()
        tail = None
        if kind == "capsule" and collider.bpy_object.children:
            tail = collider.bpy_object.children[0].matrix_world.to_translation()
        radius = getattr(collider.shape, kind).radius
    if tail is None:
        return [(Vector(head), radius)]
    centers = mapping.capsule_spheres(tuple(head), tuple(tail), radius)
    report.add(
        "colliders", "info", name,
        f"カプセルを球 {len(centers)} 個に分けました。", spheres=len(centers),
    )
    return [(Vector(c), radius) for c in centers]


def _convert_colliders(ext, armature_obj, report):
    """VRM1 コライダーグループ → 骨ごとの VRM0 コライダーグループ。{v1 uuid: [v0 uuid]} を返す。"""
    secondary = ext.vrm0.secondary_animation
    secondary.collider_groups.clear()
    colliders.clear_generated(bpy.context.scene, armature_obj)
    sb = ext.spring_bone1
    by_uuid = {c.uuid: c for c in sb.colliders}
    shape_cache = {}
    lineage = {}
    for g_index, group1 in enumerate(sb.collider_groups):
        label = group1.vrm_name or f"Group{g_index}"
        per_bone = {}
        for ref in group1.colliders:
            collider = by_uuid.get(ref.collider_uuid)
            if collider is None:
                continue
            bone = collider.node.bone_name
            if not bone or bone not in armature_obj.pose.bones:
                report.add("colliders", "lossy", label, "骨に付いていないコライダーは VRM0 で表せないため落としました。")
                continue
            if collider.uuid not in shape_cache:
                shape_cache[collider.uuid] = _collider_shapes(armature_obj, collider, report)
            per_bone.setdefault(bone, []).extend(shape_cache[collider.uuid])
        lineage[group1.uuid] = []
        # 異なる VRM1 グループは同じ骨でもまとめない（1対1の系統を保つ）
        for bone, spheres in per_bone.items():
            group0 = secondary.collider_groups.add()
            group0.uuid = uuid.uuid4().hex
            group0.node.bone_name = bone
            for n, (pos, radius) in enumerate(spheres):
                obj = colliders.make_sphere(armature_obj, bone, pos, radius, f"{label}_{bone}_{n}")
                group0.colliders.add().bpy_object = obj
            lineage[group1.uuid].append(group0.uuid)
    if not sb.collider_groups:
        report.add("colliders", "info", "collider_groups", "コライダーはありません。")
    return lineage


def _descendants(bone):
    result = []
    stack = list(bone.children)
    while stack:
        child = stack.pop()
        result.append(child)
        stack.extend(child.children)
    return result


def _deforming_bones():
    """どれかのメッシュで重みが入っている頂点グループ名。"""
    names = set()
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        indices = {g.index: g.name for g in obj.vertex_groups if g.name not in names}
        for vertex in obj.data.vertices:
            for g in vertex.groups:
                if g.weight > 0 and g.group in indices:
                    names.add(indices.pop(g.group))
            if not indices:
                break
    return names


def _parent_spring_root(roots, index, ancestors):
    root = roots[index]
    for i, other in enumerate(roots):
        if i == index or not other:
            continue
        if other in ancestors or (other == root and i < index):
            return other
    return None


def _convert_springs(ext, armature_obj, report):
    secondary = ext.vrm0.secondary_animation
    # 先に bone group を消す（古いコライダーグループへの参照が残ると Add-on がエラーを出す）
    secondary.bone_groups.clear()
    lineage = _convert_colliders(ext, armature_obj, report)
    report.summary["collider_group_map"] = lineage
    springs = ext.spring_bone1.springs
    if not springs:
        report.add("spring", "info", "springs", "揺れものはありません。")
        return
    bones = armature_obj.data.bones
    roots = [s.joints[0].node.bone_name if s.joints else "" for s in springs]
    all_joint_bones = {j.node.bone_name for s in springs for j in s.joints}
    deforming = None
    for index, spring in enumerate(springs):
        name = spring.vrm_name or f"Spring{index}"
        root = roots[index]
        if not root or root not in bones:
            report.add("spring", "lossy", name, "根元の骨がないため作りませんでした。")
            continue
        ancestors = {b.name for b in bones[root].parent_recursive}
        parent_root = _parent_spring_root(roots, index, ancestors)
        if parent_root:
            report.add(
                "spring", "lossy", name,
                f"根元 {root} が別の揺れもの（根元 {parent_root}）の下にあるため、二重に計算しないよう作りませんでした。",
                root=root, parent_root=parent_root,
            )
            continue
        joints = list(spring.joints)
        first = joints[0]
        group = secondary.bone_groups.add()
        group.comment = name
        group.stiffiness = first.stiffness
        group.gravity_power = first.gravity_power
        group.drag_force = first.drag_force
        group.hit_radius = first.hit_radius
        group.gravity_dir = mapping.vrm0_gravity_dir(tuple(first.gravity_dir))
        if first.gravity_power > 0 and abs(first.gravity_dir[0]) > 1e-6:
            report.add(
                "spring", "needs_decision", name,
                "重力に左右の向きがあります。VRM0 の値は UniVRM（Unity・Cluster）の決まりで書きました。"
                "three-vrm（aituber-kit など）は VRM0 の重力の左右を逆に扱うため、そちらでは左右が反対に揺れます。",
                gravity_dir_vrm0_json=[group.gravity_dir[0], group.gravity_dir[2], group.gravity_dir[1]],
            )
        group.center.bone_name = spring.center.bone_name
        group.bones.add().bone_name = root
        for ref in spring.collider_groups:
            for v0_uuid in lineage.get(ref.collider_group_uuid, []):
                group.collider_groups.add().collider_group_uuid = v0_uuid

        # 最後の関節は位置を決めるだけなので、値の比較から外す
        used = joints[:-1] if len(joints) > 1 else joints
        uneven = {
            key: [round(getattr(j, key), 6) for j in used]
            for key in JOINT_VALUES
            if len({round(getattr(j, key), 6) for j in used}) > 1
        }
        if len({tuple(round(v, 6) for v in j.gravity_dir) for j in used}) > 1:
            uneven["gravity_dir"] = [list(j.gravity_dir) for j in used]
        if uneven:
            report.add(
                "spring", "lossy", name,
                "関節ごとに値が違いますが、VRM0 は1つの値しか持てないため根元の関節の値を使いました。",
                joints=[j.node.bone_name for j in used], values=uneven,
            )
        extra = sorted(b.name for b in _descendants(bones[root]) if b.name not in all_joint_bones)
        if extra:
            report.add(
                "spring", "lossy", name,
                "VRM0 は根元より下の骨をすべて揺らすため、VRM1 で関節に含めていない骨も揺れます。",
                bones=extra,
            )
        last = joints[-1].node.bone_name
        if deforming is None:
            deforming = _deforming_bones()
        if last in deforming:
            report.add(
                "spring", "info", name,
                f"末端の骨 {last} が変形に使われています。VRM0 では末端にも仮想の先端が付いて揺れます。",
                bone=last,
            )


def _report_constraints(armature_obj, report):
    found = []
    for obj in bpy.data.objects:
        found += [(obj.name, c.name, c.type) for c in obj.constraints if c.type in NODE_CONSTRAINT_TYPES]
    for bone in armature_obj.pose.bones:
        found += [(bone.name, c.name, c.type) for c in bone.constraints if c.type in NODE_CONSTRAINT_TYPES]
    for owner, name, kind in found:
        report.add(
            "constraints", "lossy", owner,
            f"拘束 {name}（{kind}）は VRM0 では表せないため書き出されません。",
        )


def _summary(ext):
    sb = ext.spring_bone1
    expressions1 = ext.vrm1.expressions
    secondary = ext.vrm0.secondary_animation
    version = addon_check.find_vrm_addon_version()
    return {
        "addon_version": ".".join(str(v) for v in version) if version else None,
        "vrm1": {
            "human_bones": len(_vrm1_human_bones(ext)),
            "expressions": len(mapping.EXPRESSION_PRESETS) + len(expressions1.custom),
            "springs": len(sb.springs),
            "colliders": len(sb.colliders),
            "collider_groups": len(sb.collider_groups),
        },
        "vrm0": {
            "human_bones": sum(1 for b in ext.vrm0.humanoid.human_bones if b.node.bone_name),
            "blend_shape_groups": len(ext.vrm0.blend_shape_master.blend_shape_groups),
            "bone_groups": len(secondary.bone_groups),
            "collider_groups": len(secondary.collider_groups),
            "collider_spheres": sum(len(g.colliders) for g in secondary.collider_groups),
        },
    }


def convert_armature(armature_obj):
    """アーマチュアの VRM1 設定を VRM0 設定へ写し、Report を返す。spec_version は変えない。"""
    ext = armature_obj.data.vrm_addon_extension
    report = Report()
    _convert_humanoid(ext, report)
    _convert_meta(ext, report)
    _convert_look_at_first_person(ext, armature_obj, report)
    _convert_expressions(ext, report)
    _convert_springs(ext, armature_obj, report)
    _report_constraints(armature_obj, report)
    report.summary.update(_summary(ext))
    return report
