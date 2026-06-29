#!/usr/bin/env python3
"""Manage companies in the isolated V2 matrix.

Adds are intentionally conservative: if the shared news library contains
source-backed signals for a company, V2 writes a first-pass research column.
Otherwise it keeps the company as a pending candidate.
"""
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "v2" / "data" / "table.json"
NEWS_PATH = ROOT / "data" / "news.json"
V2_RESEARCH_PATH = ROOT / "v2" / "data" / "research_news.json"

COMPANY_ALIASES = {
    "它石智航": ["它石智航", "它石未来机器人", "上海它石未来机器人", "tashizhihang", "tashi zhihang", "TacForeSight"],
    "Sharpa": ["Sharpa", "sharpa"],
}

ROW_LABELS = [
    "核心差异化",
    "技术选择",
    "目标场景",
    "硬件能力",
    "大脑自研",
    "数据策略",
    "实测能力",
    "量产进度",
    "可靠性",
    "价格/成本",
    "真实订单",
    "标杆客户",
    "商业模式",
    "创始团队",
    "融资估值",
    "股东/生态资源",
]


def load_table():
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def save_table(table):
    TABLE_PATH.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def remove_v2_research_company(company_name):
    if not V2_RESEARCH_PATH.exists():
        return False
    try:
        data = json.loads(V2_RESEARCH_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    companies = data.get("companies")
    if not isinstance(companies, dict) or company_name not in companies:
        return False
    del companies[company_name]
    data["updated"] = data.get("updated") or ""
    V2_RESEARCH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def load_news_items():
    items = []
    if NEWS_PATH.exists():
        data = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            items.extend(data.get("items", []))
    items.extend(load_v2_research_items())
    return dedupe_news_items(items)


def load_v2_research_items():
    if not V2_RESEARCH_PATH.exists():
        return []
    try:
        data = json.loads(V2_RESEARCH_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    out = []
    for payload in (data.get("companies") or {}).values():
        if isinstance(payload, dict):
            out.extend(payload.get("items") or [])
    return out


def dedupe_news_items(items):
    out = []
    seen = set()
    for item in items:
        url = item.get("url") or ""
        key = url or norm(item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def norm(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def canonical_company_name(company_name):
    normalized = norm(company_name)
    for canonical, aliases in COMPANY_ALIASES.items():
        if normalized == norm(canonical) or any(normalized == norm(alias) for alias in aliases):
            return canonical
    return company_name.strip()


def aliases_for(company_name):
    aliases = COMPANY_ALIASES.get(company_name, [])
    return [company_name, *aliases]


def item_text(item):
    return " ".join(str(item.get(key, "")) for key in ["company", "title", "summary", "source_name", "category"])


def matching_news(company_name, items):
    aliases = [a for a in aliases_for(company_name) if a]
    hits = []
    for item in items:
        text = item_text(item)
        lowered = text.lower()
        if any(alias.lower() in lowered for alias in aliases):
            hits.append(item)
    return hits


def source_from_item(item):
    date = item.get("date") or ""
    source_name = item.get("source_name") or "新闻源"
    evidence = f"{date}，{item.get('title', '')}。"
    return {
        "name": f"{source_name} 2026-{date}" if date else source_name,
        "url": item.get("url", ""),
        "evidence": evidence,
    }


def make_cell(summary, bullets, sources=None, kind="evidence", confidence="medium", updated_recent=False, note=""):
    fallback_sources = sources or [{"name": "待核验", "url": "#", "evidence": ""}]
    return {
        "summary": summary,
        "bullets": [
            {"text": text, "sources": bullet_sources or fallback_sources}
            for text, bullet_sources in bullets
        ],
        "kind": kind,
        "updated_recent": updated_recent,
        "confidence": confidence,
        "note": note,
    }


def unknown_cell(company_name, row_label):
    return {
        "summary": "待核验",
        "bullets": [
            {
                "text": f"{company_name}该维度公开信息不足",
                "sources": [{"name": "待核验", "url": "#", "evidence": ""}],
            },
            {
                "text": "等待新增公开来源补充",
                "sources": [{"name": "待核验", "url": "#", "evidence": ""}],
            },
        ],
        "kind": "synthesis" if row_label == "核心差异化" else "evidence",
        "updated_recent": False,
        "confidence": "low",
        "note": "V2已检索当前新闻库，但该维度还没有足够公开证据。",
    }


def pending_cell(company_name, dim):
    return {
        "summary": "待核验",
        "bullets": [
            {
                "text": f"{company_name}已加入V2待评估",
                "sources": [{"name": "V2手动添加", "url": "#", "evidence": "用户在V2工作区添加"}],
            },
            {
                "text": "等待公开信息核验入库",
                "sources": [{"name": "待核验", "url": "#", "evidence": ""}],
            },
        ],
        "kind": "synthesis" if dim == "核心差异化" else "evidence",
        "updated_recent": False,
        "confidence": "low",
        "note": "V2手动候选，尚未完成长期核验。",
    }


def build_tashi_profile(company_name, hits):
    order_item = next((item for item in hits if "嘉定" in item_text(item) or "千台" in item_text(item)), None)
    tac_item = next((item for item in hits if "TacForeSight" in item_text(item) or "预判接触" in item_text(item)), None)
    if not order_item or not tac_item:
        return None

    order_source = source_from_item(order_item)
    tac_source = source_from_item(tac_item)
    both_sources = [order_source, tac_source]

    cells = {label: unknown_cell(company_name, label) for label in ROW_LABELS}
    cells.update({
        "核心差异化": make_cell(
            "工业集群+触觉预测",
            [
                ("嘉定千台级工业具身机器人集群", [order_source]),
                ("TacForeSight强化接触预判", [tac_source]),
                ("精细操作与规模部署同时推进", both_sources),
            ],
            both_sources,
            kind="synthesis",
            confidence="medium",
            note="基于两条近期公开新闻归纳，具体交付节奏仍需继续跟踪。",
        ),
        "技术选择": make_cell(
            "接触预测",
            [
                ("TacForeSight用于预测接触变化", [tac_source]),
                ("面向真实接触操作任务", [tac_source]),
                ("联合高校与研究机构发布", [tac_source]),
            ],
            [tac_source],
        ),
        "目标场景": make_cell(
            "工业精操",
            [
                ("工业具身机器人集群部署", [order_source]),
                ("擦拭、插接、拧紧等接触任务", [tac_source]),
                ("以上海嘉定为核心产业场景", [order_source]),
            ],
            both_sources,
        ),
        "硬件能力": make_cell(
            "本体待核验",
            [
                ("公开新闻强调工业具身机器人集群", [order_source]),
                ("具体本体形态与规格未披露", [order_source]),
                ("自由度、负载和成本参数待核验", [order_source]),
            ],
            [order_source],
            confidence="low",
            updated_recent=False,
            note="新闻确认部署方向，但未披露可比硬件规格。",
        ),
        "大脑自研": make_cell(
            "TacForeSight",
            [
                ("牵头发布TacForeSight", [tac_source]),
                ("聚焦接触前状态预测", [tac_source]),
                ("用于提升精细操作能力", [tac_source]),
            ],
            [tac_source],
        ),
        "数据策略": make_cell(
            "接触数据",
            [
                ("围绕真实接触操作建模", [tac_source]),
                ("擦拭、插接、拧紧任务可形成评测闭环", [tac_source]),
                ("训练数据规模与采集方式未公开", [tac_source]),
            ],
            [tac_source],
            confidence="low",
            note="方向明确，但数据规模、来源和闭环频率仍待公开。",
        ),
        "实测能力": make_cell(
            "精细接触",
            [
                ("覆盖擦拭、插接、拧紧等任务", [tac_source]),
                ("目标是破解精细操作难题", [tac_source]),
                ("连续作业指标待披露", [tac_source]),
            ],
            [tac_source],
        ),
        "量产进度": make_cell(
            "集群落地",
            [
                ("推动千台级工业具身智能机器人集群", [order_source]),
                ("计划在嘉定推进规模化部署", [order_source]),
                ("具体交付节奏仍待公开", [order_source]),
            ],
            [order_source],
            updated_recent=True,
        ),
        "可靠性": make_cell(
            "待验证",
            [
                ("规模部署计划已披露", [order_source]),
                ("连续运行和故障率指标未披露", [order_source]),
                ("需跟踪后续验收数据", [order_source]),
            ],
            [order_source],
            confidence="low",
            updated_recent=False,
            note="可靠性需要真实运行周期数据，目前只能确认部署计划。",
        ),
        "价格/成本": make_cell(
            "待披露",
            [
                ("公开新闻未披露单机价格", [order_source]),
                ("项目金额未披露", [order_source]),
                ("成本竞争力暂无法横向对比", [order_source]),
            ],
            [order_source],
            confidence="low",
            updated_recent=False,
        ),
        "真实订单": make_cell(
            "嘉定合作",
            [
                ("嘉定与上海它石未来机器人签署合作", [order_source]),
                ("目标千台级工业机器人集群落地", [order_source]),
                ("订单金额和最终交付数待公开", [order_source]),
            ],
            [order_source],
            updated_recent=True,
        ),
        "标杆客户": make_cell(
            "嘉定场景",
            [
                ("上海嘉定为明确落地场景", [order_source]),
                ("依托当地智造生态推进", [order_source]),
                ("终端客户名单待披露", [order_source]),
            ],
            [order_source],
            confidence="medium",
        ),
        "商业模式": make_cell(
            "场景部署",
            [
                ("围绕工业集群部署推进", [order_source]),
                ("商业模式可能更接近项目落地", [order_source]),
                ("收费结构和复购机制未披露", [order_source]),
            ],
            [order_source],
            confidence="low",
            updated_recent=False,
            note="只确认落地方向，不推断收入确认方式。",
        ),
        "股东/生态资源": make_cell(
            "产学合作",
            [
                ("联合新加坡国立大学等机构", [tac_source]),
                ("合作方包括上海交大、中科院自动化所、复旦", [tac_source]),
                ("嘉定产业生态提供落地资源", [order_source]),
            ],
            both_sources,
        ),
    })

    return {
        "reason": "工业集群落地 · TacForeSight接触预测",
        "cells": cells,
    }


def build_generic_profile(company_name, hits):
    if len(hits) < 2:
        return None

    sources = [source_from_item(item) for item in hits[:3]]
    headlines = [item.get("title", "") for item in hits[:3] if item.get("title")]
    source_names = {item.get("source_name") for item in hits if item.get("source_name")}
    urls = {item.get("url") for item in hits if item.get("url")}
    if len(source_names) < 2 or len(urls) < 2:
        return None

    categories = [item.get("category", "") for item in hits if item.get("category")]
    reason_bits = []
    if categories:
        reason_bits.append(categories[0])
    if headlines:
        reason_bits.append(headlines[0][:18])

    cells = {label: unknown_cell(company_name, label) for label in ROW_LABELS}
    cells["核心差异化"] = make_cell(
        "新闻待研判",
        [(title[:38], [sources[idx]]) for idx, title in enumerate(headlines[:3])],
        sources,
        kind="synthesis",
        confidence="low",
        note="V2已找到相关新闻，但尚未形成稳定竞对判断。",
    )

    category_to_rows = {
        "资本": ["融资估值"],
        "融资": ["融资估值"],
        "商业": ["真实订单", "标杆客户", "商业模式"],
        "订单": ["真实订单", "标杆客户"],
        "量产": ["量产进度", "实测能力"],
        "产品": ["技术选择", "目标场景"],
        "技术": ["技术选择", "大脑自研", "数据策略"],
    }
    for item, source in zip(hits[:3], sources):
        text = item_text(item)
        for key, labels in category_to_rows.items():
            if key not in text:
                continue
            for label in labels:
                cells[label] = make_cell(
                    "待研判",
                    [
                        (item.get("title", "")[:38], [source]),
                        ("需补充第二来源后再给出强判断", [source]),
                    ],
                    [source],
                    confidence="low",
                    note="单条新闻信号，仅作为V2候选研究起点。",
                )

    return {
        "reason": " · ".join(reason_bits) if reason_bits else "V2 新闻待研判",
        "cells": cells,
    }


def build_research_profile(company_name):
    hits = matching_news(company_name, load_news_items())
    if company_name == "它石智航":
        profile = build_tashi_profile(company_name, hits)
        if profile:
            return profile
    return build_generic_profile(company_name, hits)


def find_company_index(table, company_name):
    for idx, company in enumerate(table.get("companies", [])):
        if company.get("name") == company_name:
            return idx
    return -1


def cells_by_label(profile):
    return profile.get("cells", {}) if profile else {}


def cell_for_label(company_name, label, profile):
    researched = cells_by_label(profile).get(label)
    if researched:
        return researched
    return pending_cell(company_name, label)


def write_company_cells(table, company_idx, company_name, profile):
    for group in table.get("groups", []):
        for row in group.get("rows", []):
            cells = row.setdefault("cells", [])
            while len(cells) <= company_idx:
                cells.append(pending_cell(company_name, row.get("label", "")))
            cells[company_idx] = cell_for_label(company_name, row.get("label", ""), profile)


def add_company(table, company_name):
    company_name = canonical_company_name(company_name)
    profile = build_research_profile(company_name)
    companies = table.setdefault("companies", [])
    idx = find_company_index(table, company_name)
    if idx >= 0:
        if not profile:
            return False
        company = companies[idx]
        company.update({
            "name": company_name,
            "reason": profile["reason"],
            "emphasis": company.get("emphasis", False),
        })
        company.pop("pending", None)
        write_company_cells(table, idx, company_name, profile)
        return True

    if not profile:
        companies.append({"name": company_name, "reason": "V2 待评估", "emphasis": False, "pending": True})
        for group in table.get("groups", []):
            for row in group.get("rows", []):
                row.setdefault("cells", []).append(pending_cell(company_name, row.get("label", "")))
        return True

    companies.append({"name": company_name, "reason": profile["reason"], "emphasis": False})
    idx = len(companies) - 1
    write_company_cells(table, idx, company_name, profile)
    return True


def remove_company(table, company_name):
    company_name = canonical_company_name(company_name)
    removed_research = remove_v2_research_company(company_name)
    companies = table.get("companies", [])
    idx = next((i for i, company in enumerate(companies) if company.get("name") == company_name), -1)
    if idx < 0:
        return removed_research
    del companies[idx]
    for group in table.get("groups", []):
        for row in group.get("rows", []):
            cells = row.get("cells", [])
            if idx < len(cells):
                del cells[idx]
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--add", help="Add a company to v2/data/table.json")
    parser.add_argument("--remove", help="Remove a company from v2/data/table.json")
    args = parser.parse_args()

    if bool(args.add) == bool(args.remove):
        raise SystemExit("Pass exactly one of --add or --remove")

    table = load_table()
    if args.add:
        changed = add_company(table, args.add.strip())
    else:
        changed = remove_company(table, args.remove.strip())

    if changed:
        save_table(table)
        print("updated v2/data/table.json")
    else:
        print("no change")


if __name__ == "__main__":
    main()
