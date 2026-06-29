#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Incrementally update selected competition-matrix cells from high-confidence news.

This is intentionally conservative: it only updates known company/dimension
patterns where the news contains a concrete, source-backed event.
"""
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "data" / "table.json"
NEWS_PATH = ROOT / "data" / "news.json"


COMPANY_ALIASES = {
    "智元 AgiBot": ["智元", "智元机器人", "AGIBOT", "AgiBot"],
}

def parse_mmdd(date_str: str):
    now = datetime.now(timezone(timedelta(hours=8)))
    m = re.search(r"(\d{1,2})-(\d{1,2})", date_str or "")
    if not m:
        return None
    return datetime(now.year, int(m.group(1)), int(m.group(2)), tzinfo=now.tzinfo)


def recent_items(items, days=30):
    now = datetime.now(timezone(timedelta(hours=8)))
    out = []
    for item in items:
        dt = parse_mmdd(item.get("date", ""))
        if dt and timedelta(0) <= now - dt <= timedelta(days=days):
            out.append(item)
    return out


def item_text(item):
    return " ".join(str(item.get(k, "")) for k in ["company", "title", "summary", "source_name"])


def source_from_item(item, evidence):
    return {
        "name": f"{item.get('source_name') or '新闻源'} 2026-{(item.get('date') or '')[:2]}",
        "url": item.get("url", ""),
        "evidence": evidence,
    }


def find_company_index(table, name):
    for idx, company in enumerate(table.get("companies", [])):
        if company.get("name") == name:
            return idx
    return -1


def find_cell(table, row_label, company_idx):
    for group in table.get("groups", []):
        for row in group.get("rows", []):
            if row.get("label") == row_label:
                return row["cells"][company_idx]
    return None


def update_agibot_production(table, news_items):
    idx = find_company_index(table, "智元 AgiBot")
    if idx < 0:
        return False

    aliases = COMPANY_ALIASES["智元 AgiBot"]
    best = None
    best_count = 0
    for item in news_items:
        text = item_text(item)
        if not any(alias.lower() in text.lower() for alias in aliases):
            continue
        if not re.search(r"量产|下线|交付|产线", text):
            continue
        counts = [int(n) for n in re.findall(r"(\d{4,6})\s*台", text)]
        if not counts:
            continue
        count = max(counts)
        if count > best_count:
            best = item
            best_count = count

    if not best or best_count < 10000:
        return False

    date = best.get("date", "")
    month = date[:2].lstrip("0") or ""
    title = best.get("title", "")
    evidence = f"{date}，{title}。"
    source = source_from_item(best, evidence)
    count_text = f"{best_count}台"

    table["companies"][idx]["reason"] = f"公开披露量产规模领先 · 第{count_text}2026年{month}月下线"

    core = find_cell(table, "核心差异化", idx)
    if core:
        core.update({
            "summary": "量产规模",
            "bullets": [
                {"text": "公开披露量产规模领先", "sources": [{"name": "战略归纳", "url": "#", "evidence": ""}]},
                {"text": f"第{count_text}2026年{month}月下线", "sources": [{"name": "战略归纳", "url": "#", "evidence": ""}]},
            ],
            "updated_recent": True,
            "confidence": "medium",
            "note": f"{count_text}为明确披露节点；“领先”为公开披露口径下的竞争判断，仍需持续对比同口径出货。",
        })

    production = find_cell(table, "量产进度", idx)
    if production:
        production.update({
            "summary": f"{count_text}下线",
            "bullets": [
                {"text": f"{month}月第{count_text}精灵G2下线", "sources": [source]},
                {"text": f"{count_text}节点后继续爬坡", "sources": [source]},
                {"text": "量产进度继续构成领先项", "sources": [source]},
            ],
            "kind": "evidence",
            "updated_recent": True,
            "confidence": "high",
            "note": f"{month}月新增第{count_text}下线节点。",
        })
    return True


def main():
    if not TABLE_PATH.exists() or not NEWS_PATH.exists():
        raise SystemExit("missing data/table.json or data/news.json")
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    news = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    items = recent_items(news.get("items", []), days=30)

    changed = False
    changed = update_agibot_production(table, items) or changed

    if changed:
        TABLE_PATH.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Updated matrix from recent news.")
    else:
        print("No high-confidence matrix updates from recent news.")


if __name__ == "__main__":
    main()
