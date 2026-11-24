"""3D ビューのサイドバー「VRM」タブのパネル。"""
import bpy

from . import ops


class VRM1TO0_PT_panel(bpy.types.Panel):
    bl_idname = "VRM1TO0_PT_panel"
    bl_label = "VRM1 → VRM0 変換"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "VRM"

    def draw(self, context):
        layout = self.layout
        status, message = ops.addon_status()
        box = layout.box()
        box.label(text=message, icon={"ok": "CHECKMARK", "warn": "ERROR", "missing": "CANCEL"}[status])

        col = layout.column(align=True)
        col.label(text="開いているモデル")
        col.operator(ops.VRM1TO0_OT_copy_to_vrm0.bl_idname, icon="COPYDOWN")

        settings = context.window_manager.vrm1_to_vrm0
        col = layout.column(align=True)
        col.label(text="ファイルを変換（別の Blender で処理）")
        col.prop(settings, "input_path", text="入力")
        col.prop(settings, "output_path", text="出力")
        col.prop(settings, "overwrite")
        row = col.row()
        row.enabled = not settings.running
        row.operator(
            ops.VRM1TO0_OT_convert_file.bl_idname,
            text="変換中…" if settings.running else ops.VRM1TO0_OT_convert_file.bl_label,
            icon="EXPORT",
        )
        if settings.last_report:
            layout.label(text="レポート:")
            layout.label(text=settings.last_report)


classes = (VRM1TO0_PT_panel,)
