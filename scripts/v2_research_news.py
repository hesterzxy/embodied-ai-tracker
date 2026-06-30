#!/usr/bin/env python3
"""Fetch company-specific public signals for the V2 matrix.

This script is deliberately scoped to V2. It does not update the V1 news feed;
it writes a small evidence cache consumed by scripts/v2_company.py.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


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


def normalize_search_date(value):
    if not value:
        return datetime.now(timezone.utc).strftime("%m-%d"), datetime.now(timezone.utc)
    return fetch_news.normalize_date(value)


def search_result_item(title, url, snippet, source_name, canonical, published=""):
    date_str, dt = normalize_search_date(published)
    text = f"{title} {snippet}"
    level = fetch_news.relevance_level(title, snippet) or "核心具身"
    return {
        "date": date_str,
        "company": canonical,
        "title": normalize_title(title),
        "source_name": source_name,
        "category": "泛具身产业链" if level == "泛具身产业链" else fetch_news.categorize(title),
        "summary": fetch_news.summarize_news_text(title, snippet) or snippet[:180],
        "url": url,
        "_dt": dt,
        "_text": text,
    }


def fetch_json(url, headers=None, payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers=headers or {"User-Agent": "embodied-ai-tracker-v2"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def normalize_responses_url(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/responses"):
        return url
    if url.endswith("/v1"):
        return url + "/responses"
    return url + "/v1/responses"


def normalize_chat_url(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/chat/completions"):
        return url
    if url.endswith("/v1"):
        return url + "/chat/completions"
    return url + "/v1/chat/completions"


def search_queries(company_name, aliases):
    base = aliases[0] if aliases else company_name
    return [
        f"{base} 机器人 具身智能 量产 订单 客户",
        f"{base} 人形机器人 发布 部署 融资",
        f"{base} 官网 机器人 产品",
        f"{base} annual report robot humanoid robotics",
    ]


def parse_json_object(text):
    text = str(text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def collect_output_text(data):
    chunks = []
    if isinstance(data.get("output_text"), str):
        chunks.append(data["output_text"])
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text") or content.get("output_text")
            if isinstance(text, str):
                chunks.append(text)
    return "\n".join(chunks)


def collect_source_like_rows(value):
    rows = []
    if isinstance(value, dict):
        url = value.get("url") or value.get("source_website_url")
        title = value.get("title") or value.get("name") or value.get("caption")
        snippet = value.get("snippet") or value.get("text") or value.get("summary") or value.get("content") or ""
        published = value.get("published") or value.get("published_date") or value.get("date") or ""
        if url and title:
            rows.append({
                "title": title,
                "url": url,
                "snippet": snippet,
                "source": "AICODEWITH web_search",
                "published": published,
            })
        for child in value.values():
            rows.extend(collect_source_like_rows(child))
    elif isinstance(value, list):
        for child in value:
            rows.extend(collect_source_like_rows(child))
    return rows


def aicodewith_search_config():
    key = os.getenv("AICODEWITH_API_KEY") or ""
    base = os.getenv("OPENAI_BASE_URL") or os.getenv("AICODEWITH_BASE_URL") or ""
    model = os.getenv("AICODEWITH_SEARCH_MODEL") or os.getenv("AICODEWITH_MODEL") or os.getenv("OPENAI_MODEL") or ""
    if not key or not base or not model:
        return {"api_key": "", "responses_url": "", "chat_url": "", "model": ""}
    return {
        "api_key": key,
        "responses_url": normalize_responses_url(base),
        "chat_url": normalize_chat_url(base),
        "model": model,
    }


def web_search_aicodewith(query, limit):
    cfg = aicodewith_search_config()
    if not cfg["api_key"]:
        return []
    prompt = (
        "请联网搜索并返回真实可点击的公开来源。"
        "只关注具身智能/机器人公司动态、产品、量产、订单、客户、融资或部署。"
        f"\n搜索问题：{query}"
        "\n输出严格 JSON："
        "{\"results\":[{\"title\":\"标题\",\"url\":\"https://...\",\"snippet\":\"一句话证据摘要\",\"published\":\"YYYY-MM-DD或空\"}]}"
        f"\n最多返回 {limit} 条；不要返回百科、论坛灌水或无关泛科技内容。"
    )
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
        "User-Agent": "embodied-ai-tracker-v2",
    }
    payload = {
        "model": cfg["model"],
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "tool_choice": "required",
        "include": ["web_search_call.action.sources"],
        "input": prompt,
    }
    try:
        data = fetch_json(cfg["responses_url"], headers=headers, payload=payload)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
        data = None
    if data:
        parsed = parse_json_object(collect_output_text(data))
        rows = []
        if isinstance(parsed, dict):
            rows.extend(parsed.get("results") or [])
        rows.extend(collect_source_like_rows(data))
        out = []
        seen = set()
        for row in rows:
            url = row.get("url") or ""
            title = row.get("title") or ""
            if not url or not title or url in seen:
                continue
            seen.add(url)
            out.append({
                "title": title,
                "url": url,
                "snippet": row.get("snippet") or row.get("summary") or "",
                "source": "AICODEWITH web_search",
                "published": row.get("published") or row.get("date") or "",
            })
            if len(out) >= limit:
                return out
        if out:
            return out

    search_model = os.getenv("AICODEWITH_SEARCH_MODEL") or "gpt-5-search-api"
    chat_payload = {
        "model": search_model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 1800,
        "response_format": {"type": "json_object"},
    }
    data = fetch_json(cfg["chat_url"], headers=headers, payload=chat_payload)
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
    parsed = parse_json_object(content)
    if not isinstance(parsed, dict):
        return []
    out = []
    for row in parsed.get("results") or []:
        if row.get("title") and row.get("url"):
            out.append({
                "title": row.get("title") or "",
                "url": row.get("url") or "",
                "snippet": row.get("snippet") or "",
                "source": "AICODEWITH search",
                "published": row.get("published") or "",
            })
    return out[:limit]


def web_search_tavily(query, limit):
    key = os.getenv("TAVILY_API_KEY") or ""
    if not key:
        return []
    data = fetch_json(
        "https://api.tavily.com/search",
        headers={"Content-Type": "application/json", "User-Agent": "embodied-ai-tracker-v2"},
        payload={
            "api_key": key,
            "query": query,
            "search_depth": "advanced",
            "max_results": limit,
            "include_answer": False,
            "include_raw_content": False,
        },
    )
    out = []
    for row in data.get("results") or []:
        out.append({
            "title": row.get("title") or "",
            "url": row.get("url") or "",
            "snippet": row.get("content") or "",
            "source": "Tavily",
            "published": row.get("published_date") or "",
        })
    return out


def web_search_brave(query, limit):
    key = os.getenv("BRAVE_SEARCH_API_KEY") or ""
    if not key:
        return []
    url = "https://api.search.brave.com/res/v1/web/search?" + urlencode({"q": query, "count": min(limit, 10)})
    data = fetch_json(
        url,
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": key,
            "User-Agent": "embodied-ai-tracker-v2",
        },
    )
    out = []
    for row in ((data.get("web") or {}).get("results") or []):
        out.append({
            "title": row.get("title") or "",
            "url": row.get("url") or "",
            "snippet": row.get("description") or "",
            "source": "Brave Search",
            "published": row.get("page_age") or "",
        })
    return out


def web_search_serpapi(query, limit):
    key = os.getenv("SERPAPI_API_KEY") or ""
    if not key:
        return []
    url = "https://serpapi.com/search.json?" + urlencode({"engine": "google", "q": query, "api_key": key, "num": min(limit, 10)})
    data = fetch_json(url)
    out = []
    for row in data.get("organic_results") or []:
        out.append({
            "title": row.get("title") or "",
            "url": row.get("link") or "",
            "snippet": row.get("snippet") or "",
            "source": "SerpAPI",
            "published": row.get("date") or "",
        })
    return out


def fetch_web_search_items(company_name, aliases, days=365, limit=12):
    canonical = v2_company.canonical_company_name(company_name)
    providers = [web_search_aicodewith, web_search_tavily, web_search_brave, web_search_serpapi]
    rows = []
    stats = []
    for query in search_queries(canonical, aliases):
        provider_hits = []
        provider_name = ""
        error = ""
        for provider in providers:
            try:
                provider_hits = provider(query, limit=6)
                provider_name = provider.__name__.replace("web_search_", "")
                if provider_hits:
                    break
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                error = f"{type(exc).__name__}: {exc}"
                continue
        matched = 0
        for hit in provider_hits:
            title = fetch_news.strip_html(hit.get("title", ""))
            url = hit.get("url", "")
            snippet = fetch_news.strip_html(hit.get("snippet", ""))
            if not title or not url:
                continue
            text = f"{title} {snippet}"
            if not contains_alias(text, aliases):
                continue
            if not fetch_news.contains_any(text, fetch_news.ROBOT_SIGNAL_TERMS + fetch_news.CORE_TERMS + fetch_news.ACTION_TERMS):
                continue
            item = search_result_item(title, url, snippet, hit.get("source") or provider_name or "Web Search", canonical, hit.get("published", ""))
            rows.append(item)
            matched += 1
        stats.append({
            "name": f"web:{provider_name or 'none'}",
            "query": query,
            "fetched": bool(provider_hits),
            "error": error,
            "matched": matched,
        })
    return dedupe_items(rows)[:limit], stats


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

    web_items, web_stats = fetch_web_search_items(canonical, aliases, days=max(days, 365), limit=limit)
    found.extend(web_items)
    stats.extend(web_stats)

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
