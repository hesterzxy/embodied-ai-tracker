#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch robot/embodied-AI news from RSS feeds and update data/news.json.
Run by GitHub Actions every 4–6 hours.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import ssl
import time
from html import unescape
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")
TRANSLATION_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "title_translations.json")
DEFAULT_QWEN_API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
REPORT_CATEGORIES = ["技术突破", "产品量产", "商业订单", "资本动态", "行业动态", "泛具身产业链"]

CORE_TERMS = [
    "具身智能", "具身ai", "具身模型", "具身大脑", "具身创企", "具身创业",
    "人形机器人", "双足机器人", "四足机器人", "通用机器人", "物理 AI",
    "物理人工智能", "实体人工智能", "Physical AI",
    "VLA", "视觉语言动作", "世界模型", "机器人基础模型", "端到端机器人",
    "灵巧手", "机器人手", "机械臂", "移动操作", "全身控制", "运动控制",
    "机器人学习", "模仿学习", "强化学习", "泛化操作",
    "embodied ai", "embodied intelligence", "physical ai", "humanoid",
    "humanoid robot", "general-purpose robot", "robot foundation model",
    "robot learning", "dexterous", "dexterity", "manipulation", "mobile manipulation",
    "robot hand", "robot arm", "gripper", "quadruped", "vla", "groot",
]

PERIPHERY_TERMS = [
    "泛具身", "空间智能", "空间模型", "空间感知", "数采", "数据采集",
    "具身数据", "机器人数据", "仿真", "合成数据", "数字孪生",
    "触觉", "力控", "力传感", "传感器", "激光雷达", "深度相机", "3D视觉",
    "肌电", "肌电腕带", "编码器", "减速器", "关节", "执行器", "伺服",
    "电机", "控制器", "芯片", "边缘计算", "机器人操作系统", "ROS",
    "tactile", "haptic", "force control", "sensor", "depth camera", "lidar",
    "encoder", "actuator", "servo", "simulation", "synthetic data",
    "spatial intelligence", "robot data", "robotics data", "teleoperation",
]

COMPANY_TERMS = [
    "智元", "宇树", "银河通用", "星海图", "星动纪元", "Figure", "Optimus",
    "特斯拉", "Physical Intelligence", "优必选", "云深处", "众擎",
    "千寻智能", "大晓机器人", "傅利叶", "逐际动力", "昆仑行", "光轮智能",
    "Genesis AI", "Bear Robotics", "Intrinsic", "AGIBOT",
]

ACTION_TERMS = [
    "融资", "投资", "估值", "IPO", "上市", "并购", "收购", "发布", "推出",
    "开源", "量产", "下线", "交付", "订单", "部署", "签约", "中标",
    "落地", "商业化", "合作", "客户", "试点", "产线", "工厂",
    "funding", "raises", "raised", "investment", "ipo", "acquires", "acquisition",
    "launch", "release", "unveil", "open-source", "deploy", "deployment",
    "contract", "customer", "pilot", "partnership", "factory", "warehouse",
]

BROAD_ROBOT_TERMS = [
    "机器人", "工业机器人", "协作机器人", "移动机器人", "服务机器人", "AMR", "AGV",
    "robot", "robotics", "industrial robot", "collaborative robot",
    "warehouse robot", "autonomous mobile robot",
]

KEYWORDS = CORE_TERMS + PERIPHERY_TERMS + COMPANY_TERMS + BROAD_ROBOT_TERMS

AUTOMOTIVE_NOISE_TERMS = [
    "model s", "model 3", "model y", "model x", "cybertruck", "签名典藏版",
    "购车", "车主", "车型", "新车", "汽车", "电动车", "交付预期", "交付量",
    "销量", "续航", "充电", "超充", "方向盘", "座舱", "驾驶", "售价",
    "款车", "智驾", "自动驾驶", "辅助驾驶",
]

ROBOT_SIGNAL_TERMS = BROAD_ROBOT_TERMS + [
    "Optimus", "机器人", "人形", "机械臂", "灵巧手", "轮臂", "具身", "embodied",
]

SOURCES = [
    {"name": "量子位", "url": "https://www.qbitai.com/feed", "type": "rss"},
    {"name": "36氪", "url": "https://36kr.com/feed", "type": "rss", "strict": True},
    {"name": "雷峰网", "url": "https://www.leiphone.com/feed", "type": "rss", "strict": True},
    {"name": "钛媒体", "url": "https://www.tmtpost.com/rss.xml", "type": "rss", "strict": True},
    {"name": "爱范儿", "url": "https://www.ifanr.com/feed", "type": "rss", "strict": True},
    {"name": "InfoQ", "url": "https://www.infoq.cn/feed", "type": "rss", "strict": True},
    {"name": "IT之家", "url": "https://www.ithome.com/rss/", "type": "rss", "strict": True},
    {"name": "中国机器人网", "url": "https://www.robot-china.com/news/", "type": "html"},
    {"name": "甲子光年", "url": "https://www.jazzyear.com", "type": "html"},
    {"name": "OFweek机器人", "url": "https://robot.ofweek.com/CATList-8321200-8100-robot.html", "type": "html", "allow_patterns": [r"robot\.ofweek\.com/20\d{2}-\d{2}/ART-"], "event_required": True},
    {"name": "新战略移动机器人", "url": "https://www.xzlrobot.com/", "type": "html", "allow_patterns": [r"/news-"]},
    {"name": "中国工控网机器人", "url": "https://www.gongkong.com/robot/", "type": "html", "allow_patterns": [r"/news/2026"]},
    {"name": "The Robot Report", "url": "https://www.therobotreport.com/feed/", "type": "rss", "title_robot_signal": True},
    {"name": "TechCrunch Robotics", "url": "https://techcrunch.com/category/robotics/feed/", "type": "rss"},
    {"name": "Robotics & Automation News", "url": "https://roboticsandautomationnews.com/feed/", "type": "rss"},
    {"name": "NVIDIA Robotics", "url": "https://blogs.nvidia.com/blog/category/robotics/feed/", "type": "rss"},
    {"name": "IEEE Spectrum Robotics", "url": "https://spectrum.ieee.org/rss/robotics/fulltext", "type": "rss"},
    {"name": "RoboHub", "url": "https://robohub.org/feed/", "type": "rss"},
]

# Skip research reports / whitepapers that are not clickable news
SKIP_KEYWORDS = [
    "研报", "研究报告", "深度报告", "行业研究", "白皮书",
    "年度报告", "年度研报", "市场研究", "产业研究",
    "蓝皮书", "洞察报告", "调研报告", "分析报告",
    "早报", "晨报", "晚报", "8点1氪", "钛晨报", "今日要闻",
    "一周融资", "投融资周报", "IPO周报", "芭芭农场",
]

LOW_INFO_COMMENTARY_PATTERNS = [
    r"常见原因",
    r"避坑",
    r"避坑指南",
    r"圆桌对话",
    r"全图谱",
    r"图谱",
    r"内卷",
    r"出局\??",
    r"出路",
    r"泡沫",
    r"狂欢",
    r"经济账",
    r"合理吗",
    r"提振股价吗",
    r"信赖吗",
    r"融资暴增",
    r"没一分钱投给",
    r"普通人",
    r"值不值得",
    r"值得.*吗",
    r"有多炸裂",
    r"能有多",
    r"\bdeep dive into\b",
    r"\bwhy\b.*\bneeds? a reality check\b",
]

TITLE_NOISE_PATTERNS = [
    r"3d\s*生成",
    r"hyper3d",
    r"agenticos",
    r"机械臂支架",
    r"显示器",
    r"电竞",
    r"\b\d+k\s+\d+hz\b",
    r"车机",
    r"语音交互",
    r"移动终端",
    r"手机",
    r"apparel supply chains",
    r"fabrics",
    r"financial markets",
    r"supplier impersonation",
    r"cybersecurity",
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


def fetch_rss_once(url: str, timeout: int = 20):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
        return resp.read()


def fetch_rss(url: str, timeout: int = 20, attempts: int = 3):
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            return fetch_rss_once(url, timeout=timeout), attempt, ""
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            print(f"WARN: failed to fetch {url} attempt {attempt}/{attempts}: {last_error}")
            if attempt < attempts:
                time.sleep(min(2 ** attempt, 10))
    return None, attempts, last_error


def is_english_title(title: str) -> bool:
    return bool(re.search(r"[A-Za-z]", title or "")) and not bool(re.search(r"[\u4e00-\u9fff]", title or ""))


def has_original_title(title: str) -> bool:
    return bool(re.search(r"(?:（[^（）]*[A-Za-z][^（）]*）|\([^()]*[A-Za-z][^()]*\))$", title or ""))


def normalize_original_title_format(title: str) -> str:
    m = re.match(r"^(.*?)（([^（）]*[A-Za-z][^（）]*)）$", title or "")
    if not m:
        return title
    return f"{m.group(1).strip()} ({m.group(2).strip()})"


def normalize_chat_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/v1"):
        return url + "/chat/completions"
    if not url.endswith("/chat/completions"):
        return url + "/v1/chat/completions"
    return url


def get_llm_config():
    aicodewith_key = os.getenv("AICODEWITH_API_KEY") or ""
    if aicodewith_key:
        return {
            "provider": "aicodewith",
            "api_key": aicodewith_key,
            "api_url": normalize_chat_url(os.getenv("OPENAI_BASE_URL") or os.getenv("AICODEWITH_BASE_URL") or ""),
            "model": os.getenv("AICODEWITH_MODEL") or os.getenv("OPENAI_MODEL") or "",
        }
    qwen_key = (
        os.getenv("QWEN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("QWEN_KEY")
        or os.getenv("ALIYUN_API_KEY")
        or ""
    )
    return {
        "provider": "qwen",
        "api_key": qwen_key,
        "api_url": normalize_chat_url(os.getenv("QWEN_API_URL") or DEFAULT_QWEN_API_URL),
        "model": os.getenv("QWEN_MODEL") or "qwen-plus",
    }


def get_qwen_api_key() -> str:
    return get_llm_config()["api_key"]


def qwen_chat(messages, temperature: float = 0.1, max_tokens: int = 120) -> Optional[str]:
    llm = get_llm_config()
    if not llm["api_key"] or not llm["api_url"] or not llm["model"]:
        print(f"WARN: {llm['provider']} chat skipped: missing api key, api url, or model")
        return None
    payload = {
        "model": llm["model"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = Request(
        llm["api_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {llm['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "embodied-ai-tracker/1.0",
        },
    )
    try:
        with urlopen(req, timeout=40) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"].strip()
        return content or None
    except (KeyError, ValueError, URLError, TimeoutError, OSError) as e:
        print(f"WARN: {llm['provider']} chat failed: {type(e).__name__}: {e}")
        return None


def translate_title_with_qwen(title: str) -> Optional[str]:
    api_key = (
        get_qwen_api_key()
    )
    if not api_key:
        print("WARN: title translation skipped: no AICODEWITH_API_KEY/QWEN_API_KEY/DASHSCOPE_API_KEY/QWEN_KEY/ALIYUN_API_KEY")
        return None
    translated = qwen_chat(
        [
            {
                "role": "system",
                "content": (
                    "Translate robotics and embodied-AI news titles into concise Simplified Chinese. "
                    "Preserve company/product names. Return only the translated title."
                ),
            },
            {"role": "user", "content": title},
        ],
        temperature=0.1,
        max_tokens=120,
    )
    if translated:
        translated = translated.strip("\"'“”")
        return translated or None
    print("WARN: failed to translate title with Qwen")
    return None


def local_title_translation(title: str) -> Optional[str]:
    known = {
        "ARM Institute expands RoboticsCareer.org into physical AI": "ARM Institute将RoboticsCareer.org扩展至物理AI领域",
        "Güdel to show grinding beyond stationary robots with vertical, horizontal motion at Automate 2026": "Güdel将在Automate 2026展示具备垂直与水平运动能力的机器人打磨方案",
        "Defense manufacturing readiness hinges on autonomous finishing, says GrayMatter Robotics": "GrayMatter Robotics称国防制造准备度取决于自主表面精加工能力",
        "Is Robotic Surgery Worth Traveling Abroad for? – Patient Guide": "机器人手术是否值得出国接受？患者指南",
        "U.S. robotics industry saw double-digit growth in 2025, says IFR": "IFR称美国机器人行业在2025年实现两位数增长",
        "Video Friday: Do Robots Even Need Legs?": "视频星期五：机器人真的需要腿吗？",
        "What Amazon’s Astro Taught Me About Giving Robots a Soul": "亚马逊Astro让我理解如何赋予机器人“灵魂”",
        "Robot Talk Episode 161 – Collaborative haptic systems, with Allison Okamura": "Robot Talk第161期：Allison Okamura谈协作式触觉系统",
        "RealSense unveils AI-native D585 Pro depth camera for robots": "RealSense发布面向机器人的AI原生D585 Pro深度相机",
        "Kinova launches KIMA medical robotic arm": "Kinova发布KIMA医疗机械臂",
        "Microbot Medical to expand veteran access to robotic surgery with LIBERTY": "Microbot Medical将通过LIBERTY扩大退伍军人使用机器人手术的机会",
        "Richtech Robotics launches livestream for ADAM AI-powered humanoid": "Richtech Robotics为ADAM AI人形机器人推出直播",
        "Why Reliable Backup Power is Becoming Essential for Modern Robotics Systems": "为什么可靠备用电源正成为现代机器人系统的必需品",
        "Massachusetts awards $2 million to six local robotics companies": "马萨诸塞州向六家本地机器人公司授予200万美元资金",
        "Evaluating humanoids for surface finishing applications": "评估人形机器人在表面精加工场景中的应用",
        "Autonomique deploys semi-humanoid robots and AI at Canadian Tier 1": "Autonomique在加拿大一级供应商部署半人形机器人和AI",
        "Genesis AI launches first general-purpose humanoid robot": "Genesis AI发布首款通用人形机器人",
        "From backflips to folding laundry: How X Square Robot is building the missing ‘brain’ for embodied AI": "从后空翻到叠衣服：X Square Robot如何打造具身AI缺失的“大脑”",
        "The Secret to Marathon-Winning Humanoid Robots": "赢得马拉松的人形机器人的秘密",
        "New research enables a robot to chart a better course": "新研究让机器人能够规划更优路线",
        "Kawasaki Robotics to debut RL030N physical AI platform at Automate": "川崎机器人将在Automate首发RL030N物理AI平台",
        "Genesis AI launches Eno general-purpose robot": "Genesis AI发布Eno通用机器人",
        "How Intrinsic eliminates manual robot coding": "Intrinsic如何消除机器人手动编程",
        "Humanoid maker Agility Robotics to go public through SPAC merger": "人形机器人公司Agility Robotics将通过SPAC合并上市",
        "Bear Robotics acquires Kinisi Robotics to boost its physical AI capabilities": "Bear Robotics收购Kinisi Robotics以增强物理AI能力",
        "AGIBOT produces 15,000th robot, marking a milestone in embodied AI deployment": "智元第15000台机器人下线，标志具身AI部署进入新阶段",
        "NVIDIA releases Halos, a full-stack safety system for robotics": "NVIDIA发布面向机器人的全栈安全系统Halos",
        "Cobot’s Proxie Gen 2 robot adds autotasking, mobile manipulation": "Cobot的Proxie Gen 2机器人新增自动任务处理和移动操作能力",
        "Interview with Digid’s Nils Könne and Christian Kreil: Nanoscale sensors could help solve robotics’ tactile sensing challenge": "专访Digid的Nils Könne与Christian Kreil：纳米级传感器或可解决机器人触觉感知难题",
        "Interview with Sharpa’s Alicia Veneziani: ‘Dexterous manipulation is the key to useful humanoid robots’": "专访Sharpa的Alicia Veneziani：灵巧操作是实用人形机器人的关键",
        "Robust.AI chooses Aptiv PULSE sensor for Gen 3 Carter mobile robot": "Robust.AI为第三代Carter移动机器人选择Aptiv PULSE传感器",
        "Mantis Robotics launches dual-arm, fenceless robot": "Mantis Robotics发布双臂无围栏机器人",
    }
    return known.get(title)


def load_translation_cache():
    if os.path.exists(TRANSLATION_CACHE_PATH):
        with open(TRANSLATION_CACHE_PATH, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def save_translation_cache(cache):
    os.makedirs(os.path.dirname(TRANSLATION_CACHE_PATH), exist_ok=True)
    with open(TRANSLATION_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(cache.items())), f, ensure_ascii=False, indent=2)
        f.write("\n")


def display_title(title: str, translation_cache=None) -> str:
    title = normalize_original_title_format(title)
    if not is_english_title(title) or has_original_title(title):
        return title
    translated = None
    if translation_cache is not None:
        translated = translation_cache.get(title)
    if not translated:
        translated = local_title_translation(title) or translate_title_with_qwen(title)
        if translated and translation_cache is not None:
            translation_cache[title] = translated
    if not translated:
        return title
    return f"{translated} ({title})"


def strip_html(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\b[a-zA-Z]{1,12}>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def decode_html(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "ignore")


def contains_any(text: str, terms) -> bool:
    low = (text or "").lower()
    return any(term.lower() in low for term in terms)


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
        if "/zaobao/" in link or "/morning/" in link:
            continue
        if any(sk in title or sk in desc for sk in SKIP_KEYWORDS):
            continue
        items.append({
            "title": title,
            "url": link,
            "pub_date": pub_date,
            "description": desc,
        })
    return items


def date_from_url(url: str) -> str:
    if not url:
        return ""
    patterns = [
        r"/(20\d{2})(\d{2})/(\d{1,2})(?:/|\.|$)",
        r"/(20\d{2})[-/](\d{1,2})[-/](\d{1,2})(?:/|\.|-|_|$)",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            y, mon, day = m.groups()
            return f"{y}-{int(mon):02d}-{int(day):02d}"
    return ""


def parse_html_listing(raw: bytes, base_url: str, allow_patterns=None):
    html = decode_html(raw)
    items = []
    seen = set()
    for m in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", html, re.I | re.S):
        href = unescape(m.group(1)).strip()
        title = strip_html(m.group(2))
        if len(title) < 8:
            continue
        if href.startswith(("javascript:", "#", "mailto:")):
            continue
        url = urljoin(base_url, href)
        if allow_patterns and not any(re.search(pat, url) for pat in allow_patterns):
            continue
        if url in seen:
            continue
        seen.add(url)
        url_date = date_from_url(url)
        context = strip_html(html[max(0, m.start() - 320):m.end() + 900])
        pub_date = ""
        dm = None if url_date else re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", context)
        if url_date:
            pub_date = url_date
        elif dm:
            groups = dm.groups()
            y, mon = groups[0], groups[1]
            day = groups[2] if len(groups) > 2 else "01"
            pub_date = f"{y}-{int(mon):02d}-{int(day):02d}"
        if not pub_date:
            continue
        items.append({
            "title": title,
            "url": url,
            "pub_date": pub_date,
            "description": context,
        })
    return items[:80]


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
        ("智元", "智元机器人"), ("AGIBOT", "智元机器人"), ("Agibot", "智元机器人"),
        ("宇树", "宇树科技"), ("银河通用", "银河通用"), ("法拉第未来", "法拉第未来"),
        ("星海图", "星海图"), ("星动纪元", "星动纪元"), ("Figure", "Figure"),
        ("Agility Robotics", "Agility Robotics"), ("Agility", "Agility Robotics"),
        ("Faraday Future", "法拉第未来"),
        ("特斯拉", "特斯拉"), ("Optimus", "特斯拉"), ("OpenAI", "OpenAI"),
        ("Physical Intelligence", "Physical Intelligence"), ("优必选", "优必选"),
        ("云深处", "云深处"), ("众擎", "众擎机器人"), ("千寻智能", "千寻智能"),
    ]
    for kw, name in companies:
        if kw in title or kw.lower() in (title or "").lower():
            return name
    if any(k in title for k in ["融资", "IPO", "上市"]):
        return "行业"
    return "其他"


def excluded_by_noise(title: str, text: str) -> bool:
    t = (text or title or "").lower()
    raw = title or ""
    title_low = raw.lower()
    if contains_any(title_low, AUTOMOTIVE_NOISE_TERMS) and not contains_any(title_low, ROBOT_SIGNAL_TERMS):
        return True
    if any(re.search(pattern, raw, re.IGNORECASE) for pattern in LOW_INFO_COMMENTARY_PATTERNS):
        return True
    if any(re.search(pattern, raw, re.IGNORECASE) for pattern in TITLE_NOISE_PATTERNS):
        return True
    roundup_markers = [
        "早报", "晨报", "晚报", "8点1氪", "钛晨报", "今日要闻", "一文看懂",
        "本周", "一周", "汇总", "盘点", "合集",
    ]
    if any(k in raw for k in roundup_markers):
        return True
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
        "招聘", "裁员", "失业", "周报", "活动", "大会", "沙龙", "参会", "展会",
        "a i芯片", "ai芯片", "算力", "储能", "a idc", "aidc",
        "芭芭农场",
    ]
    has_signal = contains_any(text, CORE_TERMS + PERIPHERY_TERMS + COMPANY_TERMS)
    for kw in irrelevant_kw:
        if kw in t and not has_signal:
            return True
    return False


def relevance_level(title: str, description: str = "") -> Optional[str]:
    text = f"{title or ''} {description or ''}"
    if excluded_by_noise(title, text):
        return None

    has_core = contains_any(text, CORE_TERMS)
    has_periphery = contains_any(text, PERIPHERY_TERMS)
    has_company = contains_any(text, COMPANY_TERMS)
    has_action = contains_any(text, ACTION_TERMS)
    has_broad_robot = contains_any(text, BROAD_ROBOT_TERMS)

    if has_core:
        return "核心具身"
    if has_company and (has_action or has_broad_robot or has_periphery):
        return "核心具身"
    if has_periphery and (has_broad_robot or has_core or contains_any(text, ["具身", "人形", "机械臂", "灵巧手", "robotics", "robot"])):
        return "泛具身产业链"
    if has_broad_robot and has_action:
        return "核心具身"
    return None


def passes_source_gate(src, title: str, description: str, level: str) -> bool:
    title_text = title or ""
    if src.get("event_required") and not contains_any(
        title_text,
        [
            "融资", "投资", "IPO", "上市", "并购", "收购", "发布", "推出",
            "亮相", "量产", "交付", "订单", "签约", "合作", "投产",
            "Optimus", "优必选", "宇树", "智元", "星海图", "赛力斯",
            "云深处", "世航智能", "李开复", "极智嘉",
        ],
    ):
        return False
    if src.get("title_robot_signal") and not contains_any(
        title_text,
        ["robot", "robotics", "humanoid", "manipulation", "automation", "sensor", "机器人", "人形", "机械臂", "具身"],
    ):
        return False
    if not src.get("strict"):
        return True
    return level == "核心具身" and (
        contains_any(title_text, CORE_TERMS)
        or contains_any(title_text, COMPANY_TERMS)
        or contains_any(title_text, ["机器人", "具身智能", "Optimus", "Physical AI", "robot", "robotics", "humanoid"])
    )


def allowed_existing_item(item) -> bool:
    source = item.get("source_name", "")
    url = item.get("url", "")
    title = item.get("title", "")
    if any(x in title for x in ["1970-01-01", "参会须知", "生态沙龙", "场景应用拓展大会"]):
        return False
    if re.search(r"^\d+(\.\d+)?w\s+\d{1,2}:\d{2}", title):
        return False
    if source == "新战略移动机器人" and "/act-" in url:
        return False
    if source == "中国工控网机器人":
        if any(x in url for x in ["/select/", "/product/", "/company/"]):
            return False
        if "/news/2026" not in url:
            return False
    return True


def is_relevant(title: str) -> bool:
    return relevance_level(title) is not None


def categorize(title: str):
    t = title.lower()
    level = relevance_level(title)
    if level == "泛具身产业链":
        return "泛具身产业链"
    # 1) 资本动态：融资、IPO、并购、估值、投资
    capital_round = re.search(r"(天使|种子|pre[-\s]?[abc]|[abcde]\+?|战略|新一|上一|本)轮(融资|投资)?", t, re.I)
    if any(k in t for k in ["融资", "ipo", "上市", "估值", "募资", "并购", "收购", "投资", "funding", "raises", "raised", "acquires", "acquisition"]) or capital_round:
        if "合作" in t and not any(k in t for k in ["融资", "投资", "收购", "并购"]):
            return "产品量产"
        return "资本动态"
    # 2) 产品量产：新品、发布、量产、交付
    if any(k in t for k in ["发布", "推出", "亮相", "量产", "出货", "交付", "新品", "首台", "下线", "launch", "unveil", "release", "rollout", "ship", "produces", "production", "milestone"]):
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


def event_fingerprint(item) -> str:
    title = item.get("title", "")
    if not title:
        return ""
    text = normalize_original_title_format(title).lower()
    text = re.sub(r"\s*\([^()]*[a-z][^()]*\)\s*$", " ", text)
    text = re.sub(r"[「」“”‘’'\"｜|:：,，.。!！?？()（）\[\]【】<>《》\-_/]", " ", text)
    text = re.sub(r"\b(gen|generation|series|edition|robot|robotics)\b", " ", text)
    text = re.sub(r"(正式|宣布|今日|近日|消息|通用|具身|机器人|系列|全新|首款|美国|全美|工业级)", " ", text)
    text = re.sub(r"(精灵\s*g2|g2|futurist)", " ", text, flags=re.I)
    text = re.sub(r"\s+", "", text)

    company = extract_company(title)
    if company == "其他":
        company = ""
    action = ""
    if re.search(r"量产|下线|交付|发布|推出|亮相|投用|上市|融资|收购|并购|合作|签约|produces?|production|milestone", title, re.I):
        actions = re.findall(r"量产|下线|交付|发布|推出|亮相|投用|上市|融资|收购|并购|合作|签约|produces?|production|milestone", title, re.I)
        action = "".join(dict.fromkeys(actions))
    normalized_title = title.replace(",", "")
    nums = re.sub(r"\s+", "", "".join(re.findall(r"\d+(?:\.\d+)?\s*(?:万?台|万元|亿元|亿美元|万美元|万|亿|%|家)", normalized_title)))
    money_amounts = re.findall(r"\d+(?:\.\d+)?\s*(?:万元|亿元|亿美元|万美元|万|亿|元)", normalized_title)
    final_price = ""
    if money_amounts:
        final_price = re.sub(r"\s+", "", money_amounts[-1])
        if final_price.endswith("万") and not final_price.endswith("万元"):
            final_price += "元"
    robot_count = re.search(r"\b(\d+(?:\.\d+)?)(?:st|nd|rd|th)?\s+robot\b", normalized_title, re.I)
    if robot_count and not nums:
        nums = robot_count.group(1) + "台"
    product_match = re.search(r"(unitree\s*)?r1|精灵\s*g2|galbot\s*s1|cruzr\s*y1|faber|digit\s*v5|mantis|exr\s*[-.]?\s*2\.5", title, re.I)
    product = re.sub(r"\s+", "", product_match.group(0).lower()) if product_match else ""
    production_event = bool(nums and re.search(r"量产|下线|交付|produces?|production|milestone", title, re.I))
    if company and production_event:
        return f"{company}|{nums}|production"
    price_event = bool(nums and re.search(r"降价|降到|下调|起售|售价|现货|开售|price|pricing", title, re.I))
    if company and price_event:
        return f"{company}|{product}|{final_price or nums}|price"
    capital_event = bool(nums and re.search(r"融资|募资|投资|上市|收购|并购|ipo|spac|funding|raises|raised|acquires|acquisition", title, re.I))
    if company and re.search(r"ipo|spac|上市", title, re.I):
        return f"{company}|{product}|public-market|capital"
    if company and capital_event:
        return f"{company}|{product}|{nums}|capital"
    partnership_event = bool(company and product and re.search(r"合作|签约|部署|投用|上岗|partnership|collaborates|deploy", title, re.I))
    if partnership_event:
        return f"{company}|{product}|partnership"
    core = re.sub(r"(第|台|量产|下线|正式|通用|具身|机器人|精灵|系列|全新|首款|工业级|美国|全美)", "", text)
    core = core[:36]
    if not (company or nums or action):
        return ""
    return f"{item.get('date','')}|{company}|{nums}|{action}|{core}"


def summarize_news_text(title: str, description: str = "") -> str:
    text = strip_html(description or "")
    title_clean = strip_html(title or "")
    if title_clean:
        text = text.replace(title_clean, " ")
    text = re.sub(r"(评论|阅读原文|点击查看|当前位置：|来源：|作者：|编辑：)", " ", text)
    text = re.sub(r"\b(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})(?:\s+\d{1,2}:\d{2})?\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" |，。-")
    if not text:
        return ""
    return text[:180].rstrip("，。；;、 ") + ("…" if len(text) > 180 else "")


def summary_needs_article(summary: str) -> bool:
    if not summary or len(summary) < 25:
        return True
    noisy = [
        "javascript", "dslide", "#content", "上一篇", "下一篇", "相关新闻",
        "当前位置", "target=", "title=", "点击查看", "免责声明",
    ]
    if any(k.lower() in summary.lower() for k in noisy):
        return True
    if re.search(r"\b[a-zA-Z]{1,12}>", summary):
        return True
    if len(re.findall(r"\b\d{2}-\d{2}\b", summary)) >= 3:
        return True
    return False


def extract_article_text(raw: bytes) -> str:
    html = decode_html(raw)
    meta_patterns = [
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description["\']',
    ]
    for pattern in meta_patterns:
        m = re.search(pattern, html, re.I | re.S)
        if m:
            text = strip_html(m.group(1))
            if len(text) >= 25:
                return text

    cleaned = re.sub(r"<(script|style|nav|footer|header)\b.*?</\1>", " ", html, flags=re.I | re.S)
    paragraphs = []
    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", cleaned, re.I | re.S):
        text = strip_html(m.group(1))
        if len(text) < 24:
            continue
        if any(k in text for k in ["相关阅读", "上一篇", "下一篇", "免责声明", "扫码", "公众号"]):
            continue
        paragraphs.append(text)
        if len(" ".join(paragraphs)) > 420:
            break
    return " ".join(paragraphs)


def fetch_article_summary(url: str, title: str) -> str:
    if not url or url == "#":
        return ""
    raw, _, _ = fetch_rss(url, timeout=12, attempts=2)
    if not raw:
        return ""
    return summarize_news_text(title, extract_article_text(raw))


def parse_mmdd(date_str: str, now: Optional[datetime] = None) -> Optional[datetime]:
    if not date_str:
        return None
    now = now or datetime.now(timezone(timedelta(hours=8)))
    m = re.search(r"(\d{1,2})-(\d{1,2})", date_str)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        dt = datetime(now.year, month, day, tzinfo=now.tzinfo)
    except ValueError:
        return None
    if dt - now > timedelta(days=180):
        dt = datetime(now.year - 1, month, day, tzinfo=now.tzinfo)
    elif now - dt > timedelta(days=180):
        dt = datetime(now.year + 1, month, day, tzinfo=now.tzinfo)
    return dt


def fmt_mmdd(dt: datetime) -> str:
    return dt.strftime("%m-%d")


def current_week_range(now: Optional[datetime] = None):
    now = now or datetime.now(timezone(timedelta(hours=8)))
    start = now - timedelta(days=now.weekday())
    end = start + timedelta(days=6)
    return start, end


def latest_news_week_range(items):
    now = datetime.now(timezone(timedelta(hours=8)))
    return current_week_range(now)


def in_week(item, start: datetime, end: datetime) -> bool:
    dt = parse_mmdd(item.get("date", ""), start)
    return bool(dt and start.date() <= dt.date() <= end.date())


def trim_report_sentence(text: str, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    had_ellipsis = "…" in text
    text = text.replace("…", "")
    if not had_ellipsis and len(text) <= limit:
        return text
    parts = [part.strip() for part in re.split(r"(?<=[，,；;])", text) if part.strip()]
    if len(parts) >= 2:
        kept = ""
        for idx, part in enumerate(parts):
            if had_ellipsis and idx == len(parts) - 1:
                break
            if "…" in part and len(kept) >= 36:
                break
            if len(kept + part) > limit:
                break
            kept += part
        kept = kept.rstrip("，,；;、 ")
        if len(kept) >= 36:
            return kept
    clauses = [part.strip() for part in re.split(r"[，,；;]", text) if part.strip()]
    clauses = [part for part in clauses if "…" not in part] or clauses
    if clauses:
        return min(clauses, key=lambda part: abs(min(len(part), limit) - min(len(text), limit)))[:limit].rstrip("，,；;、 ")
    return text[:limit].rstrip("，,；;、 ")


def clean_report_fact(item) -> str:
    text = re.sub(r"\s+", " ", item.get("summary", "") or "").strip()
    if not text:
        return ""
    text = re.sub(r"^作者[｜|][^\s。！？]{1,16}\s*", "", text).strip()
    text = re.sub(r"^编辑[｜|][^\s。！？]{1,16}\s*", "", text).strip()
    text = re.sub(r"^(文|撰文)[｜|][^\s。！？]{1,16}\s*", "", text).strip()
    text = re.sub(r"^(硬氪独家|36氪|记者)?获悉[，,]\s*", "", text).strip()
    text = re.sub(r"^IT之家\s*\d+\s*月\s*\d+\s*日消息[，,]?\s*", "", text)
    text = re.sub(r"^据[^，,。]{2,16}[，,]\s*", "", text)
    text = re.sub(r"#.*$", "", text)
    text = re.sub(r"The post appeared first on .*$", "", text, flags=re.I)
    sentences = [s.strip() for s in re.split(r"(?<=[。.!?！？])\s*", text) if s.strip()]
    signal_terms = [
        "宣布", "完成", "发布", "推出", "签约", "合作", "量产", "下线", "交付",
        "融资", "投资", "备案", "订单", "部署", "投用", "上岗", "成功率",
        "触觉", "数据", "世界模型", "VLA", "工厂", "产线", "巡检", "维修",
    ]
    priority_terms = [
        "千台", "规模化部署", "落地全国首个", "本轮资金", "将主要用于",
        "完成数亿元", "完成超", "数据采集", "基础模型", "客户订单",
        "真实场景", "成功率", "量产下线",
    ]
    if sentences:
        ranked = []
        for idx, sentence in enumerate(sentences):
            score = 0
            score += sum(4 for term in priority_terms if str(term).lower() in sentence.lower())
            if contains_word(sentence, signal_terms):
                score += 2
            if re.search(r"\d", sentence):
                score += 1
            ranked.append((score, -idx, sentence))
        text = max(ranked, key=lambda row: row[:2])[2] if ranked else sentences[0]
    text = trim_report_sentence(text, 120)
    return text.rstrip("。；;，,、 ") + "。"


def report_fact_strength(item) -> int:
    title = item.get("title", "") or ""
    summary = item.get("summary", "") or ""
    text = f"{title} {summary}"
    fact = clean_report_fact(item)
    if not fact or len(fact) < 18:
        return 0
    weak_summary_patterns = [
        r"^（?财联社）?$",
        r"^（?新浪财经）?$",
        r"它们能走、能跑、能对话",
        r"机器越来越[“\"]?像人",
        r"为什么大多数机器人",
    ]
    if any(re.search(pattern, summary.strip(), re.I) for pattern in weak_summary_patterns):
        return 0
    strength = 0
    if re.search(r"\d", text):
        strength += 1
    if contains_word(text, ["完成", "宣布", "签署", "签约", "合作", "落地", "部署", "量产", "下线", "交付", "投用", "上岗", "发布", "推出"]):
        strength += 1
    if contains_word(text, ["融资", "投资", "收购", "并购", "上市", "SPAC", "订单", "客户", "工厂", "产线", "千台", "规模化", "数据采集", "基础模型"]):
        strength += 1
    if item.get("category") == "行业动态" and strength < 3:
        return 0
    return strength


def contains_word(text: str, words) -> bool:
    low = (text or "").lower()
    return any(str(word).lower() in low for word in words)


def score_report_items(items, includes, excludes=None, category_filter=None):
    excludes = excludes or []
    scored = []
    for item in items:
        if category_filter and not category_filter(item):
            continue
        text = f"{item.get('title','')} {item.get('summary','')}"
        fact_strength = report_fact_strength(item)
        if fact_strength <= 0:
            continue
        score = 0
        for group in includes:
            if contains_word(text, group["words"]):
                score += group["weight"]
        for pattern in excludes:
            if re.search(pattern, text, re.I):
                score -= 8
        score += fact_strength
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


def pick_report_items(items, limit=3):
    picked = []
    seen = set()
    for item in items:
        if not clean_report_fact(item):
            continue
        event_key = event_fingerprint(item) or title_fingerprint(item.get("title", ""))
        key = event_key or f"{item.get('company','')}|{item.get('url') or item.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        picked.append(item)
        if len(picked) >= limit:
            break
    return picked


def evidence_line(item) -> str:
    company = item.get("company") or "其他"
    title = normalize_original_title_format(item.get("title", ""))
    fact = clean_report_fact(item)
    return f"{item.get('date')}｜{item.get('category')}｜{company}｜{title}｜{fact}"


def build_report_evidence(items):
    auto_noise = [r"Model\s+[S3XY]", r"交付预期|购车|车型|车主|签名典藏版|销量"]
    themes = [
        {
            "key": "scene",
            "label": "落地验证集中在工厂、维修、巡检等可验收任务",
            "category_filter": lambda it: it.get("category") in {"产品量产", "商业订单", "技术突破", "行业动态"},
            "includes": [
                {"words": ["工厂", "产线", "维修服务", "巡检", "危险环境", "咖啡", "门店", "客户", "订单", "部署", "真实场景", "规模化部署"], "weight": 4},
                {"words": ["量产", "下线", "交付", "合作", "签约", "投用", "上岗", "发布"], "weight": 2},
                {"words": ["机器人", "人形", "具身", "机械臂", "轮臂"], "weight": 1},
            ],
        },
        {
            "key": "model",
            "label": "模型叙事正在落到真实数据和任务闭环",
            "category_filter": lambda it: it.get("category") in {"技术突破", "行业动态"},
            "includes": [
                {"words": ["世界模型", "VLA", "具身大脑", "数据", "数采", "数据飞轮", "真机", "微调", "成功率", "触觉", "感知", "强化学习"], "weight": 4},
                {"words": ["模型", "合规备案", "基础设施", "评测", "人类生成的数据"], "weight": 2},
            ],
        },
        {
            "key": "capital",
            "label": "资本更看重可定义场景和能力补齐",
            "category_filter": lambda it: it.get("category") == "资本动态",
            "includes": [
                {"words": ["融资", "投资", "IPO", "募资", "并购", "收购", "估值", "独角兽", "战略投资", "SPAC"], "weight": 4},
                {"words": ["场景", "客户", "订单", "数据基础设施", "物理AI", "世界模型"], "weight": 2},
            ],
        },
        {
            "key": "production",
            "label": "量产和价格开始成为能力验证的一部分",
            "category_filter": lambda it: it.get("category") in {"产品量产", "行业动态"},
            "includes": [
                {"words": ["量产", "下线", "第15000台", "15000台", "交付", "发布", "推出", "首秀", "产品矩阵", "降价", "2.99万"], "weight": 4},
                {"words": ["规模化", "部署", "成本", "良率", "供应链"], "weight": 2},
            ],
        },
        {
            "key": "supply",
            "label": "供应链机会要绑定具体性能瓶颈",
            "category_filter": lambda it: it.get("category") in {"泛具身产业链", "技术突破", "行业动态", "资本动态"},
            "includes": [
                {"words": ["芯片", "关节", "编码器", "减速器", "传感器", "触觉", "激光", "电池", "材料", "BOM", "供应链"], "weight": 4},
                {"words": ["控制", "力控", "执行器", "伺服", "数据采集"], "weight": 2},
            ],
        },
    ]
    evidence = []
    for theme in themes:
        scored = score_report_items(
            items,
            theme["includes"],
            excludes=auto_noise,
            category_filter=theme.get("category_filter"),
        )
        picked = pick_report_items(scored, 3)
        if picked:
            evidence.append({
                "key": theme["key"],
                "label": theme["label"],
                "items": picked,
            })
    return evidence


def local_weekly_insights(evidence, item_count=0):
    templates = {
        "scene": (
            "本周最有支撑的落地信号来自边界清楚的作业任务，{facts}。"
            "这些场景能直接看服务覆盖、连续运行、故障率和人工替代比例，比展示型动作更能验证商业化。"
        ),
        "model": (
            "技术侧更值得看的不是模型名称，而是数据如何回流到机器人能力，{facts}。"
            "如果数据采集、触觉感知和任务评测不能闭环，模型发布很难转化为稳定部署。"
        ),
        "capital": (
            "融资和并购信号需要和用途一起看，{facts}。"
            "真正有价值的是资金能否换来数据、客户、工程团队或明确场景，而不是单纯扩大“机器人”叙事。"
        ),
        "production": (
            "产品侧的重点从“发布了什么”转向“能否持续制造和部署”，{facts}。"
            "量产和价格只有和真实场景部署、数据回流、售后能力连在一起，才是有效信号。"
        ),
        "supply": (
            "上游动态的判断标准应落到部件解决什么问题，{facts}。"
            "能提升感知、力控、运动控制或量产一致性的环节，才更可能进入真实 BOM。"
        ),
    }
    insights = []
    max_insights = 3 if item_count >= 8 else 2 if item_count >= 2 else 1
    for theme in evidence:
        fact_parts = [
            clean_report_fact(item).rstrip("。！？；; ")
            for item in theme["items"][:2]
            if clean_report_fact(item)
        ]
        facts = "；".join(fact_parts)
        if not facts:
            continue
        insights.append({
            "label": theme["label"],
            "text": templates[theme["key"]].format(facts=facts),
            "evidence_urls": [item.get("url", "") for item in theme["items"][:3]],
        })
        if len(insights) >= max_insights:
            break
    if not insights:
        insights.append({
            "label": "本周无强结论",
            "text": "新闻较分散，暂时不足以支撑明确趋势判断；更适合逐条看具体公司、客户和产品指标。",
            "evidence_urls": [],
        })
    return insights


def parse_qwen_report(content: str):
    if not content:
        return None
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        text = m.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"WARN: failed to parse Qwen weekly report JSON: {e}")
        return None
    insights = data.get("insights")
    if not isinstance(insights, list) or not insights:
        return None
    cleaned = []
    for item in insights[:3]:
        label = str(item.get("label", "")).strip()
        text = str(item.get("text", "")).strip()
        text = re.sub(r"[：:]\s*", "，", text)
        text = re.sub(r"，?这对行业重要，因为", "，", text)
        text = re.sub(r"这对行业重要，因为", "", text)
        text = re.sub(r"，?这意味着", "，意味着", text)
        if label and text and "《" not in text:
            cleaned.append({"label": label[:36], "text": text[:260], "evidence_urls": []})
    if not cleaned:
        return None
    category_summaries = data.get("category_summaries") if isinstance(data.get("category_summaries"), dict) else {}
    return {"insights": cleaned, "category_summaries": category_summaries}


def generate_qwen_weekly_report(items, evidence):
    if not get_qwen_api_key() or len(items) < 2:
        return None
    evidence_text = []
    for theme in evidence[:5]:
        evidence_text.append(f"主题：{theme['label']}")
        for item in theme["items"][:3]:
            evidence_text.append(f"- {evidence_line(item)}")
    category_lines = []
    for cat in REPORT_CATEGORIES:
        cat_items = [it for it in items if it.get("category") == cat]
        if not cat_items:
            continue
        category_lines.append(f"{cat}：")
        for item in cat_items[:8]:
            category_lines.append(f"- {evidence_line(item)}")
    prompt = (
        "请基于以下具身智能周度新闻证据，生成高质量中文周报摘要。\n"
        "要求：\n"
        "1. 输出严格 JSON，不要 Markdown。\n"
        "2. insights 写 1-3 条，每条必须是“观点 + 关键事实 + 判断含义”；证据少时只写 1-2 条，不要硬凑。\n"
        "3. label 是观点短句，text 是一段完整概括；text 里不要再使用冒号。\n"
        "4. 不要使用“这对行业重要，因为”“这说明”“这意味着”这类模板化句式；把因果判断自然写进同一句话。\n"
        "5. 不要堆标题，不要出现《》引用标题，不要空泛套话。\n"
        "6. 只使用证据里的事实；证据不足就降低结论强度。\n"
        "7. category_summaries 为各分类写一句 50-90 字总结。\n"
        "JSON 格式：{\"insights\":[{\"label\":\"\",\"text\":\"\"}],\"category_summaries\":{\"技术突破\":\"\",\"产品量产\":\"\",\"商业订单\":\"\",\"资本动态\":\"\",\"行业动态\":\"\",\"泛具身产业链\":\"\"}}\n\n"
        "优先证据：\n" + "\n".join(evidence_text) + "\n\n"
        "分类新闻：\n" + "\n".join(category_lines)
    )
    content = qwen_chat(
        [
            {
                "role": "system",
                "content": "你是具身智能产业分析编辑，擅长从新闻事实中提炼具体、克制、可验证的周度趋势。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    return parse_qwen_report(content or "")


def fallback_category_summary(category: str, items) -> str:
    titles = " ".join(item.get("title", "") for item in items)
    if category == "技术突破":
        if re.search(r"世界模型|VLA|触觉|真机|数据|评测", titles, re.I):
            return "技术侧主线集中在世界模型、VLA、触觉感知和真机评测，判断标准正在从概念发布转向真实任务中的数据闭环和成功率。"
        return "技术更新指向全身协同和通用操作，行业仍在从演示能力向可复现实测能力过渡。"
    if category == "产品量产":
        if re.search(r"量产|下线|交付|维修|巡检|产线|首秀", titles):
            return "产品侧出现量产、首秀和场景服务信号，重点应继续跟踪真实部署规模、运维能力和客户复购。"
        return "产品动态偏早期发布，仍需继续跟踪交付规模和客户复购。"
    if category == "商业订单":
        return "商业化动态数量不多，优先关注是否有明确客户、订单规模、部署地点和可持续运营指标。"
    if category == "资本动态":
        return "资本动态继续围绕具身大脑、数据基础设施和明确场景展开，关键是融资后是否转化为客户、数据和交付能力。"
    if category == "行业动态":
        return "行业讨论的重点不是是否看好具身智能，而是数据、感知、执行、成本和场景验证哪一环会成为下一阶段瓶颈。"
    if category == "泛具身产业链":
        return "产业链机会需要绑定具体性能瓶颈，传感、减速器、电池和数据采集等环节只有进入量产方案才算强信号。"
    return f"本周 {category} 共 {len(items)} 条相关动态。"


def build_weekly_report(items):
    if not items:
        return {}
    start, end = latest_news_week_range(items)
    week_items = [item for item in items if in_week(item, start, end)]
    if not week_items:
        return {}
    evidence = build_report_evidence(week_items)
    qwen_report = generate_qwen_weekly_report(week_items, evidence)
    insights = local_weekly_insights(evidence, len(week_items))
    category_summaries = {}
    mode = "local"
    if qwen_report:
        insights = qwen_report["insights"]
        category_summaries = {
            cat: str(text).strip()
            for cat, text in qwen_report.get("category_summaries", {}).items()
            if str(text).strip()
        }
        mode = get_llm_config()["provider"]
    groups = []
    for cat in REPORT_CATEGORIES:
        cat_items = [item for item in week_items if item.get("category") == cat]
        if not cat_items:
            continue
        groups.append({
            "category": cat,
            "summary": category_summaries.get(cat) or fallback_category_summary(cat, cat_items),
            "items": [
                {
                    "date": item.get("date", ""),
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "company": item.get("company", ""),
                    "source_name": item.get("source_name", ""),
                }
                for item in cat_items
            ],
        })
    return {
        "start": fmt_mmdd(start),
        "end": fmt_mmdd(end),
        "generated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "mode": mode,
        "item_count": len(week_items),
        "insights": insights,
        "groups": groups,
    }


def main():
    existing = load_existing()
    translation_cache = load_translation_cache()
    existing_urls = {it.get("url", "") for it in existing.get("items", [])}
    existing_by_url = {it.get("url", ""): it for it in existing.get("items", []) if it.get("url")}
    new_items = []
    source_stats = []

    for src in SOURCES:
        raw, attempts, error = fetch_rss(src["url"], attempts=src.get("attempts", 3))
        if not raw:
            source_stats.append({
                "name": src["name"],
                "type": src["type"],
                "fetched": False,
                "attempts": attempts,
                "error": error,
                "entries": 0,
                "candidates": 0,
                "core": 0,
                "periphery": 0,
                "new": 0,
            })
            continue
        try:
            parsed = parse_html_listing(raw, src["url"], src.get("allow_patterns")) if src.get("type") == "html" else parse_rss(raw)
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            print(f"WARN: failed to parse {src['name']}: {error}")
            source_stats.append({
                "name": src["name"],
                "type": src["type"],
                "fetched": True,
                "parsed": False,
                "attempts": attempts,
                "error": error,
                "entries": 0,
                "candidates": 0,
                "core": 0,
                "periphery": 0,
                "new": 0,
            })
            continue
        candidates = 0
        core = 0
        periphery = 0
        added = 0
        for p in parsed:
            haystack = f"{p.get('title', '')} {p.get('description', '')}".lower()
            if not any(kw.lower() in haystack for kw in KEYWORDS):
                continue
            candidates += 1
            level = relevance_level(p["title"], p.get("description", ""))
            if not level:
                continue
            if not passes_source_gate(src, p["title"], p.get("description", ""), level):
                continue
            if level == "泛具身产业链":
                periphery += 1
            else:
                core += 1
            summary = summarize_news_text(p["title"], p.get("description", ""))
            if summary_needs_article(summary):
                article_summary = fetch_article_summary(p["url"], p["title"])
                if article_summary:
                    summary = article_summary
            if p["url"] in existing_urls:
                existing_item = existing_by_url.get(p["url"])
                if (
                    existing_item is not None
                    and summary
                    and (not existing_item.get("summary") or summary_needs_article(existing_item.get("summary", "")))
                ):
                    existing_item["summary"] = summary
                continue
            date_str, dt = normalize_date(p["pub_date"])
            # Keep the feed aligned with the front-end rolling 7-day window.
            if datetime.now(tz=timezone.utc) - dt > timedelta(days=7):
                continue
            new_items.append({
                "date": date_str,
                "company": extract_company(p["title"]),
                "title": display_title(p["title"], translation_cache),
                "source_name": src["name"],
                "category": "泛具身产业链" if level == "泛具身产业链" else categorize(p["title"]),
                "summary": summary,
                "url": p["url"],
            })
            added += 1
        source_stats.append({
            "name": src["name"],
            "type": src["type"],
            "fetched": True,
            "parsed": True,
            "attempts": attempts,
            "error": "",
            "entries": len(parsed),
            "candidates": candidates,
            "core": core,
            "periphery": periphery,
            "new": added,
        })
        print(f"SOURCE {src['name']}: entries={len(parsed)} candidates={candidates} core={core} periphery={periphery} new={added}")

    all_items = existing.get("items", []) + new_items
    # Deduplicate by URL and normalized title. Some publishers expose the same
    # article under multiple category URLs.
    seen_urls = set()
    seen_titles = set()
    seen_fingerprints = set()
    seen_events = set()
    deduped = []
    for it in all_items:
        if not allowed_existing_item(it):
            continue
        title_key = norm_title(it.get("title", ""))
        fp = title_fingerprint(it.get("title", ""))
        event_fp = event_fingerprint(it)
        if it["url"] and it["url"] in seen_urls:
            continue
        if title_key and title_key in seen_titles:
            continue
        if fp and fp in seen_fingerprints:
            continue
        if event_fp and event_fp in seen_events:
            continue
        seen_urls.add(it["url"])
        seen_titles.add(title_key)
        seen_fingerprints.add(fp)
        if event_fp:
            seen_events.add(event_fp)
        # 对已有新闻也应用过滤，并重新分类
        level = relevance_level(it.get("title", ""))
        if not level:
            continue
        date_str, dt = normalize_date(date_from_url(it.get("url", "")) or it.get("date", ""))
        if datetime.now(tz=timezone.utc) - dt > timedelta(days=7):
            continue
        it["date"] = date_str
        it["title"] = display_title(it.get("title", ""), translation_cache)
        it["company"] = extract_company(it.get("title", ""))
        it["summary"] = summarize_news_text(it.get("title", ""), it.get("summary", ""))
        if summary_needs_article(it.get("summary", "")):
            article_summary = fetch_article_summary(it.get("url", ""), it.get("title", ""))
            if article_summary:
                it["summary"] = article_summary
        it["category"] = "泛具身产业链" if level == "泛具身产业链" else categorize(it.get("title", ""))
        deduped.append(it)

    # Sort by date desc
    deduped.sort(key=lambda x: x.get("date", ""), reverse=True)
    # Keep last 50
    deduped = deduped[:50]

    data = {
        "updated": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "source": "RSS自动抓取",
        "source_count": len(SOURCES),
        "source_stats": source_stats,
        "weekly_report": build_weekly_report(deduped),
        "items": deduped,
    }
    save_data(data)
    save_translation_cache(translation_cache)
    print(f"Updated {DATA_PATH}: {len(new_items)} new, {len(deduped)} total.")


def probe_sources():
    for src in SOURCES:
        raw, attempts, error = fetch_rss(src["url"], attempts=src.get("attempts", 3))
        if not raw:
            print(f"PROBE {src['name']}: fetched=false attempts={attempts} error={error}")
            continue
        try:
            parsed = parse_html_listing(raw, src["url"], src.get("allow_patterns")) if src.get("type") == "html" else parse_rss(raw)
            print(f"PROBE {src['name']}: fetched=true attempts={attempts} entries={len(parsed)}")
            for p in parsed[:3]:
                print(f"  - {p.get('pub_date', '')} {p.get('title', '')}")
        except Exception as e:
            print(f"PROBE {src['name']}: fetched=true parsed=false attempts={attempts} error={type(e).__name__}: {e}")


if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe_sources()
    else:
        main()
