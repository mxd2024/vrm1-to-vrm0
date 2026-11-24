"""VRM1 → VRM0 変換アドオン。

bpy はこのファイルの先頭で import しない（mapping / report を素の Python でテストするため）。
"""


def _classes():
    from . import ops, ui

    return (*ops.classes, *ui.classes)


def register():
    import bpy

    from . import ops

    for cls in _classes():
        bpy.utils.register_class(cls)
    bpy.types.WindowManager.vrm1_to_vrm0 = bpy.props.PointerProperty(type=ops.VRM1TO0_PG_settings)


def unregister():
    import bpy

    del bpy.types.WindowManager.vrm1_to_vrm0
    for cls in reversed(_classes()):
        bpy.utils.unregister_class(cls)
