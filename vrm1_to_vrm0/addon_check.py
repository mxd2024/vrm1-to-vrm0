"""VRM Add-on for Blender の有無と版を確かめる。"""

TESTED_VERSION = (4, 4, 0)


def evaluate(version):
    """Add-on の版から (状態, 日本語メッセージ) を返す。状態は ok / warn / missing。"""
    if version is None:
        return (
            "missing",
            "VRM Add-on for Blender が有効になっていません。拡張機能から導入・有効化してください。",
        )
    shown = ".".join(str(v) for v in version)
    if tuple(version) == TESTED_VERSION:
        return ("ok", f"VRM Add-on {shown}（動作確認済み）")
    tested = ".".join(str(v) for v in TESTED_VERSION)
    return (
        "warn",
        f"VRM Add-on {shown} は未確認の版です（確認済み: {tested}）。結果をレポートで確かめてください。",
    )


def find_vrm_addon_version():
    """有効な VRM Add-on（bl_ext.*.vrm）の版を返す。なければ None。"""
    import importlib
    import os
    import tomllib

    import bpy

    for name in bpy.context.preferences.addons.keys():
        if not (name.startswith("bl_ext.") and name.endswith(".vrm")):
            continue
        module = importlib.import_module(name)
        manifest = os.path.join(os.path.dirname(module.__file__), "blender_manifest.toml")
        with open(manifest, "rb") as f:
            version = tomllib.load(f).get("version", "")
        try:
            return tuple(int(p) for p in version.split(".")[:3])
        except ValueError:
            return None
    return None
