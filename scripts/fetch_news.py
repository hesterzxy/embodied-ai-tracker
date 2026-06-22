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

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")

# Keywords to filter robot/embodied AI news
KEYWORDS = [
    "机器人", "人形", "具身智能", "embodied", "robot", "humanoid",
    "智元", "宇树", "银河通用", "星海图", "星动纪元", "Figure", "Optimus",
    "特斯拉", "Physical Intelligence", "灵巧手", "VLA", "GR00T",
    "具身大脑", "具身模型", "机器人落地",
    "robotics", "manipulation", "dexterous", "dexterity", "gripper",
    "robot arm", "robot hand", "robot learning", "robot foundation model",
    "warehouse robot", "industrial robot", "autonomous mobile robot",
]

RSS_SOURCES = [
    {"name": "量子位", "url": "https://www.qbitai.com/feed"},
    {"name": "36氪", "url": "https://36kr.com/feed"},
    {"name": "雷峰网", "url": "https://www.leiphone.com/feed"},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss.xml"},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed"},
    {"name": "The Robot Report", "url": "https://www.therobotreport.com/feed/"},
    {"name": "TechCrunch Robotics", "url": "https://techcrunch.com/category/robotics/feed/"},
    {"name": "Robotics & Automation News", "url": "https://roboticsandautomationnews.com/feed/"},
    {"name": "NVIDIA Robotics", "url": "https://blogs.nvidia.com/blog/category/robotics/feed/"},
    {"name": "IEEE Spectrum Robotics", "url": "https://spectrum.ieee.org/rss/robotics/fulltext"},
    {"name": "RoboHub", "url": "https://robohub.org/feed/"},
]

# Skip research reports / whitepapers that are not clickable news
SKIP_KEYWORDS = [
    "研报", "研究报告", "深度报告", "行业研究", "白皮书",
    "年度报告", "年度研报", "市场研究", "产业研究",
    "蓝皮书", "洞察报告", "调研报告", "分析报告",
    "早报", "晨报", "晚报", "8点1氪", "钛晨报", "今日要闻",
    "一周融资", "投融资周报", "IPO周报",
]

DIRECT_SIGNAL_KEYWORDS = [
    "具身智能", "人形机器人", "四足机器人", "机器人", "灵巧手", "机械臂",
    "具身大脑", "具身模型", "VLA", "视觉语言动作", "世界模型", "运动控制", "本体", "关节",
    "量产", "下线", "交付", "订单", "部署", "签约", "中标",
    "智元", "宇树", "银河通用", "星海图", "星动纪元", "Figure",
    "Optimus", "Physical Intelligence", "优必选", "云深处", "众擎",
    "千寻智能", "大晓机器人", "傅利叶", "逐际动力",
    "robotics", "humanoid robot", "humanoid", "robot", "robot arm",
    "robot hand", "dexterous", "manipulation", "gripper", "quadruped",
    "embodied ai", "embodied intelligence", "robot learning",
    "robot foundation model", "vla", "groot", "warehouse robot",
    "industrial robot", "autonomous mobile robot", "figure ai",
    "tesla bot", "optimus", "physical intelligence",
]

TEXT_FIELDS = [
    "title", "description", "summary",
    "{http://purl.org/rss/1.0/modules/content/}encoded",
]

DATE_FIELDS = [
    "pubDate", "published", "updated", "date",
    "{http://purl.org/dc/elements/1.1/}date",
    "{http://purl.org/dc/terms/}issued",
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


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def find_text(node, fields) -> str:
    for field in fields:
        val = node.findtext(field)
        if val:
            return strip_html(val)
    for child in node:
        local = child.tag.rsplit("}", 1)[-1]
        if local in fields and child.text:
            return strip_html(child.text)
    return ""


def find_link(node) -> str:
    link = node.findtext("link", "")
    if link:
        return link.strip()
    for child in node:
        local = child.tag.rsplit("}", 1)[-1]
        if local != "link":
            continue
        href = child.attrib.get("href", "").strip()
        rel = child.attrib.get("rel", "alternate")
        if href and rel == "alternate":
            return href
        if href and not link:
            link = href
    return link.strip()


def iter_feed_entries(root):
    channel = root.find("channel")
    if channel is not None:
        yield from channel.findall("item")
    yield from root.findall("item")
    yield from root.findall("{http://www.w3.org/2005/Atom}entry")


def parse_rss(raw: bytes):
    items = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        print(f"WARN: RSS parse error: {e}")
        return items

    for item in iter_feed_entries(root):
        title = find_text(item, ["title"])
        link = find_link(item)
        pub_date = find_text(item, DATE_FIELDS)
        desc = find_text(item, TEXT_FIELDS[1:])
        # Skip research reports
        if any(sk in title or sk in desc for sk in SKIP_KEYWORDS):
            continue
        items.append({
            "title": title,
            "url": link,
            "pub_date": pub_date,
            "description": desc,
        })
    return items


def normalize_date(pub_date: str):
    """Try to parse RSS date to MM-DD format. Returns (MM-DD, timezone-aware datetime)."""
    mmdd = re.fullmatch(r"(\d{2})-(\d{2})", pub_date or "")
    if mmdd:
        now = datetime.now(timezone.utc)
        mon, day = map(int, mmdd.groups())
        dt = datetime(now.year, mon, day, tzinfo=timezone.utc)
        if dt - now > timedelta(days=1):
            dt = datetime(now.year - 1, mon, day, tzinfo=timezone.utc)
        return dt.strftime("%m-%d"), dt

    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%a, %d %b %Y %H:%M:%S +0000",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
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


def is_relevant(title: str) -> bool:
    """判断新闻是否与具身智能相关，不相关的直接过滤掉"""
    t = title.lower()
    raw = title
    has_direct_signal = any(k.lower() in t for k in DIRECT_SIGNAL_KEYWORDS)
    # 综合资讯通常只夹带一个 AI/融资关键词，无法支撑赛道跟踪，直接过滤。
    roundup_markers = [
        "早报", "晨报", "晚报", "8点1氪", "钛晨报", "今日要闻", "一文看懂",
        "本周", "一周", "汇总", "盘点", "合集",
    ]
    if any(k in raw for k in roundup_markers):
        # 只有标题主体直接指向具身/机器人时才保留。
        if not any(k in raw for k in DIRECT_SIGNAL_KEYWORDS[:24]):
            return False
    # 不相关关键词（泛行业新闻、商业诉讼、金融市场等）：直接过滤
    irrelevant_kw = [
        "食品", "餐饮", "山崎", "奶粉", "糖", "烘焙", "美妆", "服装", "零售", "超市",
        "房价", "房产", "楼市", "物业", "家居", "建材", "酒店", "旅游", "航空", "邮轮",
        "钢铁", "煤炭", "石油", "能源", "电力", "电网", "银行", "保险", "证券", "券商",
        "基金", "股票", "A股", "美股", "港股", "原油", "黄金", "期货", "币圈",
        "诉讼", "索赔", "法院", "判决", "罚款", "违约", "破产", "清算", "重组", "退市",
        "政治", "政策", "人事", "选举", "总统", "总理", "外交", "会谈", "出访",
        "教育", "培训", "学校", "高考", "考研", "留学", "学院",
        "医疗", "医院", "医药", "药品", "疫苗", "医生", "健康", "病例", "感染",
        "疫情", "病毒", "新冠", "流感", "传染病",
        "游戏", "电影", "音乐", "综艺", "剧集", "明星", "演员", "歌手",
        "奥运", "体育", "足球", "篮球", "比赛", "赛事",
        "天气", "气候", "台风", "地震", "洪水", "灾害",
        "汽车销量", "车市", "4S店", "燃油车", "经销商",
        "手机厂商", "云台相机", "相机市场", "影像生意", "大疆", "影石",
        "高考人数", "考研人数", "就业", "毕业生",
        "外卖", "快递", "物流（非工业/机器人）",
        "超市", "便利店", "零售店",
        "家居建材", "装修", "装饰",
        "价格战", "折扣", "降价", "促销",
        "房地产", "房价", "楼市",
        "通胀", "加息", "降息", "央行", "美联储",
        "经济数据", "GDP", "CPI", "PPI", "PMI",
        "海关", "进出口", "贸易", "关税",
        "地震", "山体滑坡", "泥石流", "灾害",
        "爆炸", "火灾", "事故",
        "食品安全", "食品添加剂",
        "价格", "涨价", "降价", "定价",
        "招聘", "裁员", "失业",
    ]
    for kw in irrelevant_kw:
        if kw in t and not has_direct_signal:
            return False

    # 必须包含至少一个相关关键词（具身智能/机器人/大模型/AI）
    relevant_kw = [
        "机器人", "具身", "人形", "四足", "机械臂", "工业机器人", "服务机器人",
        "vla", "大模型", "ai", "人工智能", "自动驾驶", "自动驾驶", "智能汽车",
        "llm", "模型", "开源", "感知", "规划", "控制",
        "芯片", "gpu", "算力", "算力",
        "小米", "特斯拉", "智元", "宇树", "优必选", "云深处", "银河通用",
        "理想", "小鹏", "蔚来", "比亚迪", "车端",
        "openai", "figure", "physical intelligence",
        "deepseek", "月之暗面", "kimi", "智谱", "百川", "阿里", "腾讯", "百度",
        "机器人创业", "机器人公司", "融资", "IPO", "上市",
        "robotics", "humanoid robot", "humanoid", "robot", "robot arm",
        "robot hand", "dexterous", "manipulation", "gripper", "quadruped",
        "embodied ai", "embodied intelligence", "robot learning",
        "warehouse robot", "industrial robot", "autonomous mobile robot",
        "figure ai", "tesla bot", "optimus", "groot", "nvidia",
    ]
    # 对泛 AI/汽车/融资新闻加一道直接信号门槛，避免把无关综合新闻带进页面。
    has_relevant = any(k in t for k in relevant_kw)
    has_direct = has_direct_signal
    if any(k in t for k in ["自动驾驶", "智能汽车", "车端", "理想", "小鹏", "蔚来", "比亚迪"]):
        return has_relevant and has_direct
    if any(k in t for k in ["ai", "人工智能", "融资", "ipo", "上市", "模型", "大模型"]):
        return has_relevant and has_direct
    return has_relevant


def categorize(title: str):
    t = title.lower()
    # 1) 资本动态：融资、IPO、并购、估值、投资
    if any(k in t for k in ["融资", "ipo", "上市", "估值", "募资", "并购", "收购", "投资", "轮", "funding", "raises", "raised", "acquires", "acquisition"]):
        if "合作" in t and not any(k in t for k in ["融资", "投资", "收购", "并购"]):
            return "产品量产"
        return "资本动态"
    # 2) 产品量产：新品、发布、量产、交付
    if any(k in t for k in ["发布", "推出", "亮相", "量产", "出货", "交付", "新品", "首台", "下线", "launch", "unveil", "release", "rollout", "ship"]):
        return "产品量产"
    # 3) 商业订单：签约、订单、合同、落地
    if any(k in t for k in ["签约", "订单", "合同", "落地", "商业化", "采购", "中标", "部署", "deploy", "deployment", "customer", "contract", "partnership", "pilot"]):
        return "商业订单"
    # 4) 技术突破：大模型、VLA、算法、开源
    if any(k in t for k in ["大模型", "vla", "模型", "开源", "算法", "论文", "架构", "突破", "技术", "感知", "具身", "model", "open-source", "research", "paper", "learning", "manipulation"]):
        return "技术突破"
    # 5) 行业动态：泛行业新闻（仍需相关）
    return "行业动态"


def load_existing():
    if os.path.exists(DATA_PATH):
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"items": []}


def save_data(data):
    os.makedirs(os.path.dirname(DATA_PATH), exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def norm_title(title: str) -> str:
    return re.sub(r"\s+", "", title or "").lower()


def title_fingerprint(title: str) -> str:
    text = (title or "").lower()
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[「」“”‘’'\"｜|:：,，.。!！?？()（）\[\]【】<>《》\-_/]", " ", text)
    text = re.sub(r"\b(exclusive|first|breaking|report|报道|首发|独家|硬氪首发)\b", " ", text)
    text = re.sub(r"\b\d+(\.\d+)?\s*(million|billion|万元|亿元|美元|元|usd|rmb)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return "".join(text.split())[:80]


def main():
    existing = load_existing()
    existing_urls = {it.get("url", "") for it in existing.get("items", [])}
    new_items = []
    source_stats = []

    for src in RSS_SOURCES:
        raw = fetch_rss(src["url"])
        if not raw:
            source_stats.append({"name": src["name"], "fetched": False, "entries": 0, "candidates": 0, "relevant": 0, "new": 0})
            continue
        parsed = parse_rss(raw)
        candidates = 0
        relevant = 0
        added = 0
        for p in parsed:
            haystack = f"{p.get('title', '')} {p.get('description', '')}".lower()
            if not any(kw.lower() in haystack for kw in KEYWORDS):
                continue
            candidates += 1
            # 严格筛选：只保留具身智能相关的新闻
            if not is_relevant(p["title"]):
                continue
            relevant += 1
            if p["url"] in existing_urls:
                continue
            date_str, dt = normalize_date(p["pub_date"])
            # Keep the feed aligned with the front-end rolling 7-day window.
            if datetime.now(tz=timezone.utc) - dt > timedelta(days=7):
                continue
            new_items.append({
                "date": date_str,
                "company": extract_company(p["title"]),
                "title": p["title"],
                "source_name": src["name"],
                "category": categorize(p["title"]),
                "url": p["url"],
            })
            added += 1
        source_stats.append({
            "name": src["name"],
            "fetched": True,
            "entries": len(parsed),
            "candidates": candidates,
            "relevant": relevant,
            "new": added,
        })
        print(f"SOURCE {src['name']}: entries={len(parsed)} candidates={candidates} relevant={relevant} new={added}")

    all_items = existing.get("items", []) + new_items
    # Deduplicate by URL and normalized title. Some publishers expose the same
    # article under multiple category URLs.
    seen_urls = set()
    seen_titles = set()
    seen_fingerprints = set()
    deduped = []
    for it in all_items:
        title_key = norm_title(it.get("title", ""))
        fp = title_fingerprint(it.get("title", ""))
        if it["url"] and it["url"] in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if fp and fp in seen_fingerprints:
            continue
        seen_urls.add(it["url"])
        seen_titles.add(title_key)
        seen_fingerprints.add(fp)
        # 对已有新闻也应用过滤，并重新分类
        if not is_relevant(it.get("title", "")):
            continue
        date_str, dt = normalize_date(it.get("date", ""))
        if datetime.now(tz=timezone.utc) - dt > timedelta(days=7):
            continue
        it["date"] = date_str
        it["category"] = categorize(it.get("title", ""))
        deduped.append(it)

    # Sort by date desc
    deduped.sort(key=lambda x: x.get("date", ""), reverse=True)
    # Keep last 50
    deduped = deduped[:50]

    data = {
        "updated": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "source": "RSS自动抓取",
        "source_count": len(RSS_SOURCES),
        "source_stats": source_stats,
        "items": deduped,
    }
    save_data(data)
    print(f"Updated {DATA_PATH}: {len(new_items)} new, {len(deduped)} total.")


if __name__ == "__main__":
    main()
