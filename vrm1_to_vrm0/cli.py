"""画面なし実行口。

blender -b --python-exit-code 1 --python vrm1_to_vrm0/cli.py -- <入力.vrm> [<出力.vrm>] [--overwrite]

終了コード: 0 = 成功、1 = 変換失敗、2 = 前提不足。標準出力の最後の行は `REPORT: <json のパス>`
（レポートを書けなかったときは `REPORT: ` だけ）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vrm1_to_vrm0 import pipeline  # noqa: E402


def _parse(argv):
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    overwrite = "--overwrite" in args
    paths = [a for a in args if a != "--overwrite"]
    if not paths or len(paths) > 2:
        return None
    return paths[0], (paths[1] if len(paths) == 2 else None), overwrite


def _flush_all():
    """Python と C ランタイムの標準出力バッファを先に出し切る（Blender 本体の表示が後ろに回らないように）。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except Exception:
            pass
    try:
        import ctypes

        ctypes.CDLL("ucrtbase").fflush(None)
    except Exception:
        pass


def _out(line):
    """途中で sys.stdout が差し替えられても UTF-8 で出すため、ファイル記述子 1 に直接書く。"""
    os.write(1, (line + "\n").encode("utf-8"))


def _finish(code):
    """ほかのアドオンが終了時に標準出力へ書くと REPORT 行が最後でなくなるため、ここで終わらせる。"""
    os._exit(code)


def main():
    parsed = _parse(sys.argv)
    if parsed is None:
        _flush_all()
        _out("使い方: blender -b --python cli.py -- <入力.vrm> [<出力.vrm>] [--overwrite]")
        _out("REPORT: ")
        _finish(2)
    in_path, out_path, overwrite = parsed
    code, report, json_path = pipeline.convert_file(in_path, out_path, overwrite)
    counts = report.counts()
    _flush_all()
    _out(f"STATUS: {report.summary.get('status')} (exit {code})")
    _out(f"COUNTS: needs_decision={counts['needs_decision']} lossy={counts['lossy']} info={counts['info']}")
    if code != 0:
        for item in report.items:
            if item.target in ("run", "error"):
                _out(f"ERROR: {item.message}")
    _out(f"REPORT: {json_path or ''}")
    _finish(code)


main()
