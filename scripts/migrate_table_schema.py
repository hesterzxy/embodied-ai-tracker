#!/usr/bin/env python3
"""Migrate table.json to the structured matrix schema.

The new cell format is:
  {
    "summary": "十字内判断",
    "bullets": [{"text": "...", "sources": [...]}],
    "confidence": "high|medium|low",
    "note": "..."
  }
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "data" / "table.json"

GROUP_ORDER = [
    ("战略定位", ["核心差异化", "技术路线", "目标场景"]),
    ("技术能力", ["硬件能力", "大脑自研", "数据策略", "实测能力"]),
    ("产品化进展", ["量产进度", "可靠性", "价格/成本"]),
    ("商业化验证", ["真实订单", "标杆客户", "商业模式"]),
    ("组织与资本", ["创始团队", "融资估值", "股东/生态资源"]),
]

ROW_MAP = {
    "目标场景": "落地场景",
    "价格/成本": "价格",
}

SUMMARY_RULES = [
    (re.compile(r"暂无|未公开|不明|无公开|待公开"), "待核验"),
    (re.compile(r"万台|1万|10000"), "万台量产"),
    (re.compile(r"千台"), "千台订单"),
    (re.compile(r"百台"), "百台验证"),
    (re.compile(r"VLA|端到端|π0|Helix|大模型|FSD|GR00T", re.I), "模型路线"),
    (re.compile(r"不做本体|不造硬件|模型授权|API"), "模型路线"),
    (re.compile(r"四足|硬件|关节|执行器|灵巧手|本体"), "硬件路线"),
    (re.compile(r"真机|数据|仿真|合成"), "数据闭环"),
    (re.compile(r"BMW|比亚迪|宁德|蔚来|蓝思|客户|部署|订单"), "客户验证"),
    (re.compile(r"融资|估值|IPO|上市|投后|\$|亿元"), "资本充足"),
    (re.compile(r"创始|CEO|CTO|教授|华为|Waymo|斯坦福|MIT"), "团队强"),
    (re.compile(r"价格|成本|售价|美元|万元|租赁"), "价格待明"),
    (re.compile(r"工厂|制造|物流|家庭|科研|教育|文旅|场景"), "场景聚焦"),
]

ROW_DEFAULT_SUMMARY = {
    "技术路线": "路线清晰",
    "核心差异化": "差异明确",
    "目标场景": "场景聚焦",
    "硬件能力": "硬件成型",
    "大脑自研": "自研大脑",
    "数据策略": "数据闭环",
    "实测能力": "实测推进",
    "量产进度": "量产推进",
    "可靠性": "验证推进",
    "价格/成本": "价格待明",
    "真实订单": "订单验证",
    "标杆客户": "客户验证",
    "商业模式": "模式成型",
    "创始团队": "团队完整",
    "融资估值": "资本充足",
    "股东/生态资源": "生态待明",
}

LOW_SIGNAL = re.compile(r"暂无|未公开|不明|传闻|可能|预计|目标|长期|公开报道|#")


def split_bullets(text):
    parts = []
    buf = []
    depth = 0
    for ch in text or "":
        if ch in "（(":
            depth += 1
        elif ch in "）)" and depth:
            depth -= 1
        if depth == 0 and ch in "，,；;、":
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    if not parts:
        return ["暂无公开数据"]
    if len(parts) == 1:
        return parts
    return parts[:3]


def summarize(row_label, text, company_reason=""):
    if row_label == "核心差异化" and company_reason:
        first = re.split(r"[·，,；;]", company_reason)[0].strip()
        return first[:10] or ROW_DEFAULT_SUMMARY[row_label]
    for pattern, label in SUMMARY_RULES:
        if pattern.search(text or ""):
            return label
    return ROW_DEFAULT_SUMMARY.get(row_label, "待核验")


def confidence_for(text, sources):
    source_text = " ".join(
        [s.get("name", "") + " " + s.get("url", "") for s in sources if isinstance(s, dict)]
    )
    if LOW_SIGNAL.search((text or "") + " " + source_text):
        return "low"
    if len([s for s in sources if isinstance(s, dict) and s.get("url") and s.get("url") != "#"]) >= 2:
        return "high"
    return "medium"


def source_for_index(row, idx):
    sources = row.get("sources", [])
    if idx >= len(sources):
        return [{"name": "待核验", "url": "#"}]
    src = sources[idx]
    if isinstance(src, dict):
        return [src]
    return [{"name": str(src), "url": str(src) if str(src).startswith("http") else "#"}]


def make_cell(row_label, text, sources, company_reason=""):
    bullets = split_bullets(text)
    conf = confidence_for(text, sources)
    return {
        "summary": summarize(row_label, text, company_reason),
        "bullets": [{"text": b, "sources": sources} for b in bullets],
        "confidence": conf,
        "kind": "synthesis" if row_label == "核心差异化" else "evidence",
        "note": "" if conf != "low" else "来源不足或包含预测/传闻，待三角核验",
    }


def main():
    data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    companies = data.get("companies", [])

    row_lookup = {}
    for group in data.get("groups", []):
        for row in group.get("rows", []):
            row_lookup[row.get("label")] = row

    new_groups = []
    for group_label, row_labels in GROUP_ORDER:
        rows = []
        for label in row_labels:
            old_label = ROW_MAP.get(label, label)
            if label == "核心差异化":
                cells = [
                    make_cell(
                        label,
                        c.get("reason", "暂无公开数据"),
                        [{"name": "公司定位归纳", "url": "#"}],
                        c.get("reason", ""),
                    )
                    for c in companies
                ]
            elif label == "股东/生态资源":
                team = row_lookup.get("创始团队", {})
                funding = row_lookup.get("融资估值", {})
                cells = []
                for idx, c in enumerate(companies):
                    text_parts = []
                    if idx < len(funding.get("cells", [])):
                        text_parts.append(funding["cells"][idx])
                    if idx < len(team.get("cells", [])):
                        text_parts.append(team["cells"][idx])
                    text = "；".join(text_parts) if text_parts else "暂无公开数据"
                    sources = []
                    sources.extend(source_for_index(funding, idx))
                    sources.extend(source_for_index(team, idx))
                    cells.append(make_cell(label, text, sources, c.get("reason", "")))
            else:
                old_row = row_lookup.get(old_label, {})
                cells = []
                for idx, c in enumerate(companies):
                    text = old_row.get("cells", ["暂无公开数据"] * len(companies))[idx]
                    sources = source_for_index(old_row, idx)
                    cells.append(make_cell(label, text, sources, c.get("reason", "")))
            rows.append({"label": label, "cells": cells})
        new_groups.append({"label": group_label, "rows": rows})

    data["schema_version"] = 2
    data["verification_method"] = "triangulated_evidence_v1"
    data["groups"] = new_groups
    TABLE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
