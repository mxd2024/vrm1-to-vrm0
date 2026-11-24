"""Blender テスト共通の小道具。"""
import json
import os
import struct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "tests", "out")
FIXTURE_DIR = os.path.join(OUT, "fixtures")
# 実際のアバターでの回帰テストに使う VRM1（件数は作者の手元のモデルに合わせてある）。未設定なら飛ばす。
SAMPLE_VRM = os.environ.get("VRM1TO0_SAMPLE_VRM", "")
HAS_SAMPLE = bool(SAMPLE_VRM) and os.path.exists(SAMPLE_VRM)
SAMPLE_SKIP_REASON = "環境変数 VRM1TO0_SAMPLE_VRM（実際のアバターの VRM1）が未設定"


def read_glb_json(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, _version, _length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF", path
    chunk_length, chunk_type = struct.unpack_from("<I4s", data, 12)
    assert chunk_type == b"JSON"
    return json.loads(data[20:20 + chunk_length].decode("utf-8"))


def load_vrm(path):
    """空のシーンに VRM を読み込み、アーマチュアを返す。"""
    import bpy

    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.vrm(filepath=path)
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    assert len(armatures) == 1, armatures
    return armatures[0]


def fixture_path(kind):
    """fixture がなければ作り、パスを返す。"""
    from tests.blender import fixtures

    path = os.path.join(FIXTURE_DIR, f"{kind}.vrm")
    if not os.path.exists(path):
        fixtures.make_fixture(kind, path)
    return path


def true_eye_position(path):
    """VRM1 ファイルのノード階層から、視線の位置（Blender のワールド座標）を求める。"""
    from mathutils import Matrix, Quaternion, Vector

    data = read_glb_json(path)
    nodes = data["nodes"]
    vrm = data["extensions"]["VRMC_vrm"]
    parent = {c: i for i, nd in enumerate(nodes) for c in nd.get("children", [])}

    def local(nd):
        x, y, z, w = nd.get("rotation", [0, 0, 0, 1])
        return (
            Matrix.Translation(nd.get("translation", [0, 0, 0]))
            @ Quaternion((w, x, y, z)).to_matrix().to_4x4()
            @ Matrix.Diagonal((*nd.get("scale", [1, 1, 1]), 1))
        )

    index = vrm["humanoid"]["humanBones"]["head"]["node"]
    matrix = Matrix()
    while index is not None:
        matrix = local(nodes[index]) @ matrix
        index = parent.get(index)
    eye = matrix @ Vector(vrm["lookAt"]["offsetFromHeadBone"])
    return Vector((eye.x, -eye.z, eye.y))


def vrm0_eye_position(armature_obj):
    """VRM0 設定欄の視線の位置（Blender のワールド座標）。VRM0 の頭ノードは回転を持たない。"""
    from mathutils import Vector

    fp = armature_obj.data.vrm_addon_extension.vrm0.first_person
    head = armature_obj.data.bones[fp.first_person_bone.bone_name]
    x, y, z = fp.first_person_bone_offset
    return (armature_obj.matrix_world @ head.head_local) + Vector((-x, -y, z))


def items(report, section=None, kind=None):
    return [
        i for i in report.items
        if (section is None or i.section == section) and (kind is None or i.kind == kind)
    ]
