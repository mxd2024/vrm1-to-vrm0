import json
import os
import shutil
import unittest

from vrm1_to_vrm0.report import Report, write_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "tests", "out", "日本語 フォルダ")


def sample_report():
    report = Report(summary={"input": "a.vrm"})
    report.add("spring", "info", "Hair", "球5つに分けました", count=5)
    report.add("expressions", "lossy", "Joy", "抑制設定が消えます")
    report.add("meta", "needs_decision", "credit_notation", "対応欄なし")
    return report


class ReportTest(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(OUT_DIR, ignore_errors=True)

    def test_counts(self):
        self.assertEqual(sample_report().counts(), {"info": 1, "lossy": 1, "needs_decision": 1})

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            Report().add("meta", "warning", "x", "y")

    def test_write_json_and_markdown_to_japanese_path(self):
        json_path, md_path = write_report(sample_report(), os.path.join(OUT_DIR, "a_vrm0.vrm"))
        self.assertEqual(json_path, os.path.join(OUT_DIR, "a_vrm0.vrm.report.json"))
        self.assertEqual(md_path, os.path.join(OUT_DIR, "a_vrm0.vrm.report.md"))
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["summary"], {"input": "a.vrm"})
        self.assertEqual(data["counts"], {"info": 1, "lossy": 1, "needs_decision": 1})
        self.assertEqual(data["items"][0]["detail"], {"count": 5})
        self.assertEqual(data["items"][2]["kind"], "needs_decision")

    def test_markdown_lists_needs_decision_first(self):
        _, md_path = write_report(sample_report(), os.path.join(OUT_DIR, "a_vrm0.vrm"))
        with open(md_path, encoding="utf-8") as f:
            text = f.read()
        self.assertLess(text.index("## 要判断"), text.index("## 失われた・近似した"))
        self.assertLess(text.index("## 失われた・近似した"), text.index("## 規則どおり"))
        self.assertIn("credit_notation", text)


if __name__ == "__main__":
    unittest.main()
