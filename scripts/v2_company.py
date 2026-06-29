#!/usr/bin/env python3
"""Manage companies in the isolated V2 matrix."""
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TABLE_PATH = ROOT / "v2" / "data" / "table.json"


def load_table():
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


def save_table(table):
    TABLE_PATH.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def add_company(table, company_name):
    companies = table.setdefault("companies", [])
    if any(c.get("name") == company_name for c in companies):
        return False
    companies.append({"name": company_name, "reason": "V2 待评估", "emphasis": False, "pending": True})
    for group in table.get("groups", []):
        for row in group.get("rows", []):
            row.setdefault("cells", []).append(pending_cell(company_name, row.get("label", "")))
    return True


def remove_company(table, company_name):
    companies = table.get("companies", [])
    idx = next((i for i, company in enumerate(companies) if company.get("name") == company_name), -1)
    if idx < 0:
        return False
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
