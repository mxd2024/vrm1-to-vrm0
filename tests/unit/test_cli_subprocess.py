"""CLI を別プロセスの Blender で動かす（日本語・空白を含むパス）。"""
import os
import shutil
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe"
CLI = os.path.join(ROOT, "vrm1_to_vrm0", "cli.py")
SAMPLE_VRM = os.environ.get("VRM1TO0_SAMPLE_VRM", "")
OUT_DIR = os.path.join(ROOT, "tests", "out", "cli 日本語")


def run_cli(*args):
    proc = subprocess.run(
        [BLENDER, "-b", "--python-exit-code", "1", "--python", CLI, "--", *args],
        capture_output=True, timeout=600,
    )
    lines = proc.stdout.decode("utf-8", errors="replace").rstrip("\r\n").splitlines()
    return proc.returncode, lines


@unittest.skipUnless(os.path.exists(BLENDER) and SAMPLE_VRM and os.path.exists(SAMPLE_VRM), "Blender か、環境変数 VRM1TO0_SAMPLE_VRM の VRM1 がない")
class CliTest(unittest.TestCase):
    def test_convert_success(self):
        shutil.rmtree(OUT_DIR, ignore_errors=True)
        out = os.path.join(OUT_DIR, "サンプル_vrm0.vrm")
        code, lines = run_cli(SAMPLE_VRM, out)
        self.assertEqual(code, 0, lines[-20:])
        self.assertTrue(lines[-1].startswith("REPORT: "), lines[-5:])
        report_path = lines[-1][len("REPORT: "):]
        self.assertEqual(os.path.normcase(report_path), os.path.normcase(out + ".report.json"))
        self.assertTrue(os.path.exists(report_path))
        self.assertTrue(os.path.exists(out))

    def test_missing_input_exits_2(self):
        code, lines = run_cli(os.path.join(OUT_DIR, "ない.vrm"))
        self.assertEqual(code, 2, lines[-20:])
        self.assertEqual(lines[-1], "REPORT: ")


if __name__ == "__main__":
    unittest.main()
