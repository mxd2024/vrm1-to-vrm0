"""読み込み → 写し替え → VRM0 で書き出し → 読み直して比較 → レポート、を一度に行う（画面なし用）。"""
import os
import struct
import json
import traceback
from contextlib import contextmanager

import bpy

from . import addon_check
from .convert import convert_armature
from .report import Report, write_report

# 書き出し後に消えて当然の拡張（VRM0 の形に写し替え済み）
CONVERTED_EXTENSIONS = {"VRMC_vrm", "VRMC_springBone", "VRMC_materials_mtoon"}
EXTENSION_SECTION = {
    "VRMC_node_constraint": "constraints",
    "VRMC_springBone_extended_collider": "colliders",
}
META_FIELDS = (
    "title", "version", "author", "contact_information", "reference", "allowed_user_name",
    "violent_ussage_name", "sexual_ussage_name", "commercial_ussage_name",
    "license_name", "other_license_url",
)


def default_output_path(in_path):
    stem, _ext = os.path.splitext(in_path)
    return stem + "_vrm0.vrm"


def _read_glb_json(path):
    with open(path, "rb") as f:
        header = f.read(20)
        _magic, _version, _length, chunk_length, _chunk_type = struct.unpack("<4sIII4s", header)
        return json.loads(f.read(chunk_length).decode("utf-8"))


@contextmanager
def _auto_license_confirmation():
    """自分で書き出した VRM0 を確認のために読み直すときだけ、利用条件の確認画面を省く。"""
    key = "BLENDER_VRM_AUTOMATIC_LICENSE_CONFIRMATION"
    old = os.environ.get(key)
    os.environ[key] = "true"
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old


def _load(path):
    bpy.ops.wm.read_homefile(use_empty=True)
    bpy.ops.import_scene.vrm(filepath=path)
    return [o for o in bpy.data.objects if o.type == "ARMATURE"]


def _snapshot(ext):
    """VRM0 設定欄の、読み直しで比べる値。"""
    v0 = ext.vrm0
    secondary = v0.secondary_animation
    groups = v0.blend_shape_master.blend_shape_groups
    return {
        "human_bones": sum(1 for b in v0.humanoid.human_bones if b.node.bone_name),
        "blend_shape_groups": len(groups),
        "blend_shape_names": sorted(g.name for g in groups),
        "binds": sum(len(g.binds) for g in groups),
        "material_values": sum(len(g.material_values) for g in groups),
        "bone_groups": len(secondary.bone_groups),
        "spring_root_bones": sum(len(g.bones) for g in secondary.bone_groups),
        "collider_groups": len(secondary.collider_groups),
        "collider_spheres": sum(len(g.colliders) for g in secondary.collider_groups),
        "meta": {key: getattr(v0.meta, key) for key in META_FIELDS},
    }


def compare_roundtrip(in_path, out_path, expected=None):
    """出力 VRM0 を読み直し、写し替え直後の VRM0 設定（expected）と並べた dict を返す。"""
    if expected is None:
        armatures = _load(in_path)
        convert_armature(armatures[0])
        expected = _snapshot(armatures[0].data.vrm_addon_extension)
    with _auto_license_confirmation():
        armatures = _load(out_path)
    if len(armatures) != 1:
        raise RuntimeError(f"出力を読み直せませんでした（アーマチュア {len(armatures)} 個）")
    actual = _snapshot(armatures[0].data.vrm_addon_extension)
    return {
        key: {"expected": expected[key], "actual": actual[key], "match": expected[key] == actual[key]}
        for key in expected
    }


def _report_lost_extensions(in_path, out_path, report):
    before = set(_read_glb_json(in_path).get("extensionsUsed", []))
    after = set(_read_glb_json(out_path).get("extensionsUsed", []))
    for name in sorted(before - after - CONVERTED_EXTENSIONS):
        report.add(
            EXTENSION_SECTION.get(name, "materials"), "lossy", name,
            f"拡張 {name} は VRM0 の書き出しで失われました。",
        )


def convert_file(in_path, out_path=None, overwrite=False):
    """戻り値: (終了コード, Report, レポート JSON のパス or None)。0=成功 1=失敗 2=前提不足。"""
    in_path = os.path.abspath(in_path)
    out_path = os.path.abspath(out_path or default_output_path(in_path))
    report = Report(summary={"input": in_path, "output": out_path})

    def stop(code, message):
        report.summary["status"] = "failed" if code == 1 else "precondition"
        report.add("meta", "needs_decision", "run", message)
        return code, report, None

    if not os.path.isfile(in_path):
        return stop(2, f"入力ファイルがありません: {in_path}")
    try:
        extensions = _read_glb_json(in_path).get("extensions", {})
    except Exception:
        return stop(2, f"VRM ファイルとして読めません: {in_path}")
    if "VRMC_vrm" not in extensions:
        if "VRM" in extensions:
            return stop(2, "VRM0 のファイルです（入力は VRM1 にしてください）。")
        return stop(2, "VRM ファイルではありません（VRMC_vrm がありません）。")
    if os.path.exists(out_path) and not overwrite:
        return stop(1, f"出力が既にあります（上書きするには --overwrite）: {out_path}")
    status, message = addon_check.evaluate(addon_check.find_vrm_addon_version())
    if status == "missing":
        return stop(2, message)
    if os.path.normcase(in_path) == os.path.normcase(out_path):
        return stop(2, "入力と出力が同じファイルです。")

    try:
        armatures = _load(in_path)
        if len(armatures) != 1:
            return stop(2, f"アーマチュアがちょうど1つではありません（{len(armatures)} 個）。")
        arm = armatures[0]
        ext = arm.data.vrm_addon_extension
        if ext.spec_version != "1.0":
            return stop(2, f"VRM1 のファイルではありません（spec_version={ext.spec_version}）。")
        converted = convert_armature(arm)
        converted.summary = {**report.summary, **converted.summary}
        report = converted
        if status == "warn":
            report.add("meta", "info", "addon_version", message)
        expected = _snapshot(ext)
        ext.spec_version = "0.0"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        result = bpy.ops.export_scene.vrm(
            filepath=out_path, armature_object_name=arm.name, ignore_warning=True
        )
        if result != {"FINISHED"} or not os.path.isfile(out_path):
            raise RuntimeError(f"VRM0 の書き出しに失敗しました: {result}")
        roundtrip = compare_roundtrip(in_path, out_path, expected)
        report.summary["roundtrip"] = roundtrip
        for key, value in roundtrip.items():
            if not value["match"]:
                report.add("meta", "needs_decision", f"roundtrip.{key}", "読み直した値が書き出し前と違います。", **value)
        _report_lost_extensions(in_path, out_path, report)
        report.summary["status"] = "ok"
        json_path, _md_path = write_report(report, out_path)
        return 0, report, json_path
    except Exception:
        report.summary["status"] = "failed"
        report.add("meta", "needs_decision", "error", "変換中にエラーが起きました。", traceback=traceback.format_exc())
        json_path = None
        if os.path.isdir(os.path.dirname(out_path)):
            json_path, _ = write_report(report, out_path)
        return 1, report, json_path
