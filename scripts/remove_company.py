#!/usr/bin/env python3
"""Remove one company column from data/table.json."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "data" / "table.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("company")
    args = parser.parse_args()

    data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    companies = data.get("companies", [])
    keep = [c.get("name") != args.company for c in companies]
    if all(keep):
        print(f"{args.company} not found")
        return

    data["companies"] = [c for c, k in zip(companies, keep) if k]
    for group in data.get("groups", []):
        for row in group.get("rows", []):
            if "cells" in row:
                row["cells"] = [cell for cell, k in zip(row["cells"], keep) if k]
            if "sources" in row:
                row["sources"] = [src for src, k in zip(row["sources"], keep) if k]

    TABLE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"removed {args.company}")


if __name__ == "__main__":
    main()
