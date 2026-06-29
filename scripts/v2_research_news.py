#!/usr/bin/env python3
"""Fetch company-specific public signals for the V2 matrix.

This script is deliberately scoped to V2. It does not update the V1 news feed;
it writes a small evidence cache consumed by scripts/v2_company.py.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
V2_RESEARCH_PATH = ROOT / "v2" / "data" / "research_news.json"

sys.path.insert(0, str(SCRIPT_DIR))
import fetch_news  # noqa: E402
import v2_company  # noqa: E402


def now_iso():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def load_cache():
    if not V2_RESEARCH_PATH.exists():
        return {"updated": "", "companies": {}}
    try:
        data = json.loads(V2_RESEARCH_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"updated": "", "companies": {}}
    if not isinstance(data, dict):
        return {"updated": "", "companies": {}}
    data.setdefault("companies", {})
    return data


def save_cache(cache):
    V2_RESEARCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    V2_RESEARCH_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def aliases_for(company_name):
    aliases = v2_company.aliases_for(company_name)
    clean = []
    for alias in aliases:
        alias = str(alias or "").strip()
        if alias and alias not in clean:
            clean.append(alias)
    return clean


def contains_alias(text, aliases):
    lowered = (text or "").lower()
    compact = re.sub(r"\s+", "", lowered)
    for alias in aliases:
        low = alias.lower()
        if low in lowered:
            return True
        if re.sub(r"\s+", "", low) in compact:
            return True
    return False


def normalize_title(title):
    title = fetch_news.normalize_original_title_format(title or "")
    translated = fetch_news.local_title_translation(title)
    if translated and translated not in title:
        return f"{translated} ({title})"
    return title


def item_from_parsed(parsed, src, level):
    date_str, dt = fetch_news.normalize_date(parsed.get("pub_date", ""))
    summary = fetch_news.summarize_news_text(parsed.get("title", ""), parsed.get("description", ""))
    return {
        "date": date_str,
        "company": src.get("company_name", "其他"),
        "title": normalize_title(parsed.get("title", "")),
        "source_name": src.get("name", "新闻源"),
        "category": "泛具身产业链" if level == "泛具身产业链" else fetch_news.categorize(parsed.get("title", "")),
        "summary": summary,
        "url": parsed.get("url", ""),
        "_dt": dt,
    }


def relevant_to_company(parsed, src, aliases):
    text = f"{parsed.get('title', '')} {parsed.get('description', '')}"
    if not contains_alias(text, aliases):
        return None
    level = fetch_news.relevance_level(parsed.get("title", ""), parsed.get("description", ""))
    if not level:
        has_robot_signal = fetch_news.contains_any(text, fetch_news.ROBOT_SIGNAL_TERMS + fetch_news.ACTION_TERMS)
        if not has_robot_signal:
            return None
        level = "核心具身"
    if not fetch_news.passes_source_gate(src, parsed.get("title", ""), parsed.get("description", ""), level):
        company_specific_signal = fetch_news.contains_any(text, fetch_news.ROBOT_SIGNAL_TERMS + fetch_news.CORE_TERMS + fetch_news.ACTION_TERMS)
        if not company_specific_signal:
            return None
        if not fetch_news.contains_any(text, fetch_news.ROBOT_SIGNAL_TERMS + fetch_news.CORE_TERMS):
            return None
        if not fetch_news.contains_any(text, fetch_news.ACTION_TERMS):
            return None
        return level
    return level


def dedupe_items(items):
    out = []
    seen = set()
    for item in sorted(items, key=lambda row: row.get("_dt") or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        key = item.get("url") or fetch_news.title_fingerprint(item.get("title", ""))
        if not key or key in seen:
            continue
        seen.add(key)
        clean = {k: v for k, v in item.items() if k != "_dt"}
        out.append(clean)
    return out


def fetch_company_news(company_name, days=30, limit=12):
    canonical = v2_company.canonical_company_name(company_name)
    aliases = aliases_for(canonical)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    found = []
    stats = []

    for src in fetch_news.SOURCES:
        raw, attempts, error = fetch_news.fetch_rss(src["url"], attempts=src.get("attempts", 2))
        stat = {
            "name": src["name"],
            "fetched": bool(raw),
            "attempts": attempts,
            "error": error,
            "matched": 0,
        }
        if not raw:
            stats.append(stat)
            continue
        try:
            parsed_items = (
                fetch_news.parse_html_listing(raw, src["url"], src.get("allow_patterns"))
                if src.get("type") == "html"
                else fetch_news.parse_rss(raw)
            )
        except Exception as exc:
            stat["error"] = f"{type(exc).__name__}: {exc}"
            stats.append(stat)
            continue

        src_for_item = dict(src)
        src_for_item["company_name"] = canonical
        for parsed in parsed_items:
            level = relevant_to_company(parsed, src, aliases)
            if not level:
                continue
            date_str, dt = fetch_news.normalize_date(parsed.get("pub_date", ""))
            if datetime.now(timezone.utc) - dt > timedelta(days=days):
                continue
            if dt < cutoff:
                continue
            item = item_from_parsed({**parsed, "pub_date": date_str}, src_for_item, level)
            item["_dt"] = dt
            found.append(item)
            stat["matched"] += 1
        stats.append(stat)

    return canonical, dedupe_items(found)[:limit], stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", required=True, help="Company name to research for V2")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args()

    canonical, items, stats = fetch_company_news(args.company.strip(), args.days, args.limit)
    cache = load_cache()
    cache["updated"] = now_iso()
    cache.setdefault("companies", {})[canonical] = {
        "queried_at": now_iso(),
        "query": args.company.strip(),
        "canonical_name": canonical,
        "days": args.days,
        "items": items,
        "source_stats": stats,
    }
    save_cache(cache)
    print(f"V2 research fetched {len(items)} item(s) for {canonical}")


if __name__ == "__main__":
    main()
