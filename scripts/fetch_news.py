#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch robot/embodied-AI news from RSS feeds and update data/news.json.
Run by GitHub Actions every 4–6 hours.
"""
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")

# Keywords to filter robot/embodied AI news
KEYWORDS = [
    "机器人", "人形", "具身智能", "embodied", "robot", "humanoid",
    "智元", "宇树", "银河通用", "星海图", "星动纪元", "Figure", "Optimus",
    "特斯拉", "Physical Intelligence", "灵巧手", "VLA", "GR00T"
]

RSS_SOURCES = [
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss"},
    {"name": "量子位", "url": "https://www.qbitai.com/feed"},
    {"name": "甲子光年", "url": "https://www.jazzyear.com/feed"},
    {"name": "智东西", "url": "https://www.zhidx.com/feed"},
    {"name": "36氪", "url": "https://36kr.com/feed"},
    {"name": "雷峰网", "url": "https://www.leiphone.com/feed"},
    {"name": "虎嗅网", "url": "https://www.huxiu.com/rss/0.xml"},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss.xml"},
    {"name": "界面新闻", "url": "https://www.jiemian.com/lists/42.html"},
    {"name": "创业邦", "url": "https://www.cyzone.cn/feed/"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed"},
    {"name": "品玩", "url": "https://www.pingwest.com/feed/"},
    {"name": "动点科技", "url": "https://techcrunch.cn/feed"},
    {"name": "AI科技评论", "url": "https://aitechtalk.com/feed"},
    {"name": "机器人大讲堂", "url": "https://www.robo-report.com/feed"},
    {"name": "高工机器人", "url": "https://www.gongkong.com/rss/robot.xml"},
]

# Skip research reports / whitepapers that are not clickable news
SKIP_KEYWORDS = [
    "研报", "研究报告", "深度报告", "行业研究", "白皮书",
    "年度报告", "年度研报", "市场研究", "产业研究",
    "蓝皮书", "洞察报告", "调研报告", "分析报告",
]


def fetch_rss(url: str, timeout: int = 20):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception as e:
        # Catch all network / SSL / timeout / HTTP errors — don't let one bad source kill the whole run
        print(f"WARN: failed to fetch {url}: {type(e).__name__}: {e}")
        return None


def parse_rss(raw: bytes):
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"WARN: RSS parse error: {e}")
        return items

    channel = root.find("channel")
    if channel is None:
        channel = root

    for item in channel.findall("item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", item.findtext("dc:date", "")).strip()
        desc = item.findtext("description", "").strip()
        # Skip research reports
        if any(sk in title or sk in desc for sk in SKIP_KEYWORDS):
            continue
        if any(kw in title or kw in desc for kw in KEYWORDS):
            items.append({
                "title": title,
                "url": link,
                "pub_date": pub_date,
                "description": desc,
            })
    return items


def normalize_date(pub_date: str):
    """Try to parse RSS date to MM-DD format. Returns (MM-DD, timezone-aware datetime)."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S +0000",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(pub_date, fmt)
            # Make timezone-aware: if no tz, assume UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%m-%d"), dt
        except ValueError:
            continue
    # Fallback: regex extract date
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', pub_date)
    if m:
        y, mon, d = m.groups()
        dt = datetime(int(y), int(mon), int(d), tzinfo=timezone.utc)
        return f"{mon}-{d}", dt
    now = datetime.now(timezone.utc)
    return now.strftime("%m-%d"), now


def extract_company(title: str):
    companies = [
        ("智元", "智元机器人"), ("宇树", "宇树科技"), ("银河通用", "银河通用"),
        ("星海图", "星海图"), ("星动纪元", "星动纪元"), ("Figure", "Figure"),
        ("特斯拉", "特斯拉"), ("Optimus", "特斯拉"), ("OpenAI", "OpenAI"),
        ("Physical Intelligence", "Physical Intelligence"), ("优必选", "优必选"),
        ("云深处", "云深处"), ("众擎", "众擎机器人"), ("千寻智能", "千寻智能"),
    ]
    for kw, name in companies:
        if kw in title:
            return name
    if any(k in title for k in ["融资", "IPO", "上市"]):
        return "行业"
    return "其他"


def categorize(title: str):
    t = title.lower()
    if any(k in t for k in ["融资", "ipo", "上市", "估值", "募资", "轮"]):
        return "融资"
    if any(k in t for k in ["发布", "推出", "亮相", "合作", "签约", "开源", "新品"]):
        return "新品与合作"
    if any(k in t for k in ["成立", "新公司", "天使轮", "浮出水面"]):
        return "新公司"
    return "其他"


def load_existing():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": []}


def save_data(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    existing = load_existing()
    existing_urls = {it.get("url", "") for it in existing.get("items", [])}
    new_items = []

    for src in RSS_SOURCES:
        raw = fetch_rss(src["url"])
        if not raw:
            continue
        parsed = parse_rss(raw)
        for p in parsed:
            if p["url"] in existing_urls:
                continue
            date_str, dt = normalize_date(p["pub_date"])
            # Only keep items from last 14 days to avoid stale news
            if datetime.now(tz=timezone.utc) - dt > timedelta(days=14):
                continue
            new_items.append({
                "date": date_str,
                "company": extract_company(p["title"]),
                "title": p["title"],
                "source_name": src["name"],
                "category": categorize(p["title"]),
                "url": p["url"],
            })

    all_items = existing.get("items", []) + new_items
    # Deduplicate by URL
    seen = set()
    deduped = []
    for it in all_items:
        if it["url"] and it["url"] in seen:
            continue
        seen.add(it["url"])
        deduped.append(it)

    # Sort by date desc
    deduped.sort(key=lambda x: x.get("date", ""), reverse=True)
    # Keep last 50
    deduped = deduped[:50]

    data = {
        "updated": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "source": "RSS自动抓取",
        "items": deduped,
    }
    save_data(data)
    print(f"Updated {DATA_PATH}: {len(new_items)} new, {len(deduped)} total.")


if __name__ == "__main__":
    main()
