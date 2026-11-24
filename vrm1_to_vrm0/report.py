"""変換レポート（JSON と Markdown）。bpy に依存しない。"""
import json
import os
from dataclasses import asdict, dataclass, field

KINDS = ("needs_decision", "lossy", "info")


@dataclass
class ReportItem:
    section: str
    kind: str
    target: str
    message: str
    detail: dict = field(default_factory=dict)


@dataclass
class Report:
    summary: dict = field(default_factory=dict)
    items: list = field(default_factory=list)

    def add(self, section, kind, target, message, **detail):
        if kind not in KINDS:
            raise ValueError(f"unknown kind: {kind}")
        item = ReportItem(section, kind, target, message, detail)
        self.items.append(item)
        return item

    def extend(self, items):
        self.items.extend(items)

    def counts(self):
        result = {kind: 0 for kind in ("info", "lossy", "needs_decision")}
        for item in self.items:
            result[item.kind] += 1
        return result

    def to_dict(self):
        return {
            "summary": self.summary,
            "counts": self.counts(),
            "items": [asdict(item) for item in self.items],
        }


_HEADINGS = {
    "needs_decision": "要判断（人か AI が決めること）",
    "lossy": "失われた・近似した項目",
    "info": "規則どおりの変換",
}


def to_markdown(report):
    lines = ["# VRM1 → VRM0 変換レポート", "", "## 概要", ""]
    for key, value in report.summary.items():
        lines.append(f"- {key}: {value}")
    counts = report.counts()
    lines += [
        "",
        f"件数: 要判断 {counts['needs_decision']} / 失われた・近似 {counts['lossy']} / 規則どおり {counts['info']}",
    ]
    for kind in KINDS:
        items = [i for i in report.items if i.kind == kind]
        lines += ["", f"## {_HEADINGS[kind]}（{len(items)}件）", ""]
        if not items:
            lines.append("なし")
        for item in items:
            lines.append(f"- [{item.section}] **{item.target}**: {item.message}")
            if item.detail:
                lines.append(f"  - detail: `{json.dumps(item.detail, ensure_ascii=False)}`")
    return "\n".join(lines) + "\n"


def write_report(report, out_vrm_path):
    """<出力パス>.report.json と .report.md を書き、2つのパスを返す。"""
    folder = os.path.dirname(os.path.abspath(out_vrm_path))
    os.makedirs(folder, exist_ok=True)
    json_path = out_vrm_path + ".report.json"
    md_path = out_vrm_path + ".report.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.to_dict(), f, ensure_ascii=False, indent=2, default=str)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(to_markdown(report))
    return json_path, md_path
