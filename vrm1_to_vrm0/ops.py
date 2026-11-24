"""2つの操作: 開いているモデルの VRM0 設定へ写す／ファイルを別プロセスで変換して書き出す。"""
import os
import subprocess
import tempfile

import bpy
from bpy.props import BoolProperty, StringProperty

from . import addon_check
from .report import to_markdown

REPORT_TEXT = "VRM0_conversion_report.md"
CLI_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cli.py")


def addon_status():
    return addon_check.evaluate(addon_check.find_vrm_addon_version())


# ---- 別プロセスでの変換（開いているファイルには何も読み込まない） ----

def start_conversion(in_path, out_path, overwrite):
    """画面なしの Blender で cli.py を起動し、待つための情報を返す。"""
    log = tempfile.NamedTemporaryFile(prefix="vrm1_to_vrm0_", suffix=".log", delete=False)
    args = [bpy.app.binary_path, "-b", "--python-exit-code", "1", "--python", CLI_PATH, "--", in_path]
    if out_path:
        args.append(out_path)
    if overwrite:
        args.append("--overwrite")
    proc = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT)
    log.close()
    return {"proc": proc, "log": log.name}


def needs_retry(code, attempts):
    """CLI の終了コード（0/1/2）以外で終わった＝Blender が異常終了した。1回だけやり直す。

    ほかのアドオンが起動直後に別スレッドから Blender のデータを書き換え、画面なしの Blender が
    まれに落ちることがある（本アドオンの処理より前）。
    """
    return code not in (0, 1, 2) and attempts < 2


def poll_conversion(job):
    """終わっていなければ None。終わっていれば (終了コード, レポート JSON のパス or None, 出力の行)。"""
    code = job["proc"].poll()
    if code is None:
        return None
    with open(job["log"], "rb") as f:
        lines = f.read().decode("utf-8", errors="replace").splitlines()
    try:
        os.remove(job["log"])
    except OSError:
        pass
    report_path = None
    for line in reversed(lines):
        if line.startswith("REPORT: "):
            report_path = line[len("REPORT: "):].strip() or None
            break
    return code, report_path, lines


class VRM1TO0_OT_copy_to_vrm0(bpy.types.Operator):
    bl_idname = "vrm1_to_vrm0.copy_to_vrm0"
    bl_label = "VRM0 設定へ写す"
    bl_description = "選択中のアーマチュアの VRM1 設定を VRM0 設定へ写します（VRM1 側は変えません）"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != "ARMATURE" or addon_status()[0] == "missing":
            return False
        # VRM0 のモデルで実行すると、手で作った VRM0 設定を空の VRM1 設定で上書きしてしまう
        if obj.data.vrm_addon_extension.spec_version != "1.0":
            cls.poll_message_set("VRM1 のモデル（VRM のバージョンが 1.0）を選んでください。")
            return False
        return True

    def execute(self, context):
        from .convert import convert_armature

        report = convert_armature(context.active_object)
        text = bpy.data.texts.get(REPORT_TEXT) or bpy.data.texts.new(REPORT_TEXT)
        text.clear()
        text.write(to_markdown(report))
        counts = report.counts()
        self.report(
            {"INFO"},
            f"VRM0 設定へ写しました。要判断 {counts['needs_decision']} 件・失われた {counts['lossy']} 件"
            f"（テキスト「{REPORT_TEXT}」）",
        )
        return {"FINISHED"}


class VRM1TO0_OT_convert_file(bpy.types.Operator):
    bl_idname = "vrm1_to_vrm0.convert_file"
    bl_label = "VRM1 → VRM0 に変換して書き出す"
    bl_description = "VRM1 ファイルを別の Blender で読み込み、VRM0 に変換して書き出します（開いているファイルは変えません）"

    input_path: StringProperty(name="入力", subtype="FILE_PATH")
    output_path: StringProperty(name="出力", subtype="FILE_PATH")
    overwrite: BoolProperty(name="上書き", default=False)

    _timer = None
    _job = None
    _attempts = 0

    @classmethod
    def poll(cls, context):
        return addon_status()[0] != "missing"

    def invoke(self, context, event):
        settings = context.window_manager.vrm1_to_vrm0
        self.input_path = bpy.path.abspath(settings.input_path)
        self.output_path = bpy.path.abspath(settings.output_path) if settings.output_path else ""
        self.overwrite = settings.overwrite
        return self.execute(context)

    def execute(self, context):
        if not self.input_path or not os.path.isfile(self.input_path):
            self.report({"ERROR"}, "入力の VRM ファイルを指定してください。")
            return {"CANCELLED"}
        self._job = start_conversion(self.input_path, self.output_path or None, self.overwrite)
        self._attempts = 1
        context.window_manager.vrm1_to_vrm0.running = True
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        self.report({"INFO"}, "変換を始めました…")
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        """途中でファイルを開き直したときなど。ボタンを使える状態に戻す。"""
        if self._timer is not None:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.window_manager.vrm1_to_vrm0.running = False

    def modal(self, context, event):
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        result = poll_conversion(self._job)
        if result is None:
            return {"PASS_THROUGH"}
        if needs_retry(result[0], self._attempts):
            self._attempts += 1
            self._job = start_conversion(self.input_path, self.output_path or None, self.overwrite)
            self.report({"WARNING"}, "変換用の Blender が途中で終了したため、もう一度実行しています…")
            return {"PASS_THROUGH"}
        context.window_manager.event_timer_remove(self._timer)
        settings = context.window_manager.vrm1_to_vrm0
        settings.running = False
        code, report_path, lines = result
        settings.last_report = report_path or ""
        status = next((line for line in reversed(lines) if line.startswith("COUNTS: ")), "")
        if code == 0:
            self.report({"INFO"}, f"変換しました。{status[len('COUNTS: '):]} レポート: {report_path}")
            return {"FINISHED"}
        errors = [line[len("ERROR: "):] for line in lines if line.startswith("ERROR: ")]
        message = errors[-1] if errors else f"終了コード {code}"
        self.report({"ERROR"}, f"変換できませんでした: {message}")
        return {"CANCELLED"}


class VRM1TO0_PG_settings(bpy.types.PropertyGroup):
    input_path: StringProperty(name="入力（VRM1）", subtype="FILE_PATH")
    output_path: StringProperty(name="出力（空なら <入力>_vrm0.vrm）", subtype="FILE_PATH")
    overwrite: BoolProperty(name="同名ファイルを上書き", default=False)
    running: BoolProperty(default=False)
    last_report: StringProperty(default="")


classes = (VRM1TO0_PG_settings, VRM1TO0_OT_copy_to_vrm0, VRM1TO0_OT_convert_file)
