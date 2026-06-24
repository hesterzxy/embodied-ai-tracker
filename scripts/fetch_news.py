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
import ssl
from html import unescape
from datetime import datetime, timezone, timedelta
from typing import Optional
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from urllib.error import URLError

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "news.json")
QWEN_API_URL = os.getenv(
    "QWEN_API_URL",
    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
)
QWEN_MODEL = os.getenv("QWEN_MODEL", "qwen-plus")

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
    "Genesis AI", "Bear Robotics", "Intrinsic",
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
    r"小鹏gx",
    r"agenticos",
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


def fetch_rss(url: str, timeout: int = 20):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
            return resp.read()
    except Exception as e:
        # Catch all network / SSL / timeout / HTTP errors — don't let one bad source kill the whole run
        print(f"WARN: failed to fetch {url}: {type(e).__name__}: {e}")
        return None


def is_english_title(title: str) -> bool:
    return bool(re.search(r"[A-Za-z]", title or "")) and not bool(re.search(r"[\u4e00-\u9fff]", title or ""))


def has_original_title(title: str) -> bool:
    return bool(re.search(r"（[^（）]*[A-Za-z][^（）]*）$", title or ""))


def translate_title_with_qwen(title: str) -> Optional[str]:
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": QWEN_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Translate robotics and embodied-AI news titles into concise Simplified Chinese. "
                    "Preserve company/product names. Return only the translated title."
                ),
            },
            {"role": "user", "content": title},
        ],
        "temperature": 0.1,
        "max_tokens": 120,
    }
    req = Request(
        QWEN_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "embodied-ai-tracker/1.0",
        },
    )
    try:
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        translated = data["choices"][0]["message"]["content"].strip()
        translated = translated.strip("\"'“”")
        return translated or None
    except (KeyError, ValueError, URLError, TimeoutError, OSError) as e:
        print(f"WARN: failed to translate title with Qwen: {type(e).__name__}: {e}")
        return None


def local_title_translation(title: str) -> Optional[str]:
    known = {
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
        "Bear Robotics acquires Kinisi Robotics to boost its physical AI capabilities": "Bear Robotics收购Kinisi Robotics以增强物理AI能力",
        "NVIDIA releases Halos, a full-stack safety system for robotics": "NVIDIA发布面向机器人的全栈安全系统Halos",
        "Cobot’s Proxie Gen 2 robot adds autotasking, mobile manipulation": "Cobot的Proxie Gen 2机器人新增自动任务处理和移动操作能力",
        "Interview with Digid’s Nils Könne and Christian Kreil: Nanoscale sensors could help solve robotics’ tactile sensing challenge": "专访Digid的Nils Könne与Christian Kreil：纳米级传感器或可解决机器人触觉感知难题",
        "Interview with Sharpa’s Alicia Veneziani: ‘Dexterous manipulation is the key to useful humanoid robots’": "专访Sharpa的Alicia Veneziani：灵巧操作是实用人形机器人的关键",
    }
    return known.get(title)


def display_title(title: str) -> str:
    if not is_english_title(title) or has_original_title(title):
        return title
    translated = local_title_translation(title) or translate_title_with_qwen(title)
    if not translated:
        return title
    return f"{translated}（{title}）"


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", unescape(text)).strip()


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


def parse_html_listing(raw: bytes, base_url: str, allow_patterns=None):
    html = raw.decode("utf-8", "ignore")
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
        context = strip_html(html[max(0, m.start() - 180):m.end() + 180])
        pub_date = ""
        dm = re.search(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})", context)
        if not dm:
            dm = re.search(r"/(20\d{2})(\d{2})/(\d{1,2})/", url)
        if not dm:
            dm = re.search(r"/(20\d{2})(\d{2})/", url)
        if dm:
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


def excluded_by_noise(title: str, text: str) -> bool:
    t = (text or title or "").lower()
    raw = title or ""
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

    for src in SOURCES:
        raw = fetch_rss(src["url"])
        if not raw:
            source_stats.append({"name": src["name"], "type": src["type"], "fetched": False, "entries": 0, "candidates": 0, "core": 0, "periphery": 0, "new": 0})
            continue
        parsed = parse_html_listing(raw, src["url"], src.get("allow_patterns")) if src.get("type") == "html" else parse_rss(raw)
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
            if p["url"] in existing_urls:
                continue
            date_str, dt = normalize_date(p["pub_date"])
            # Keep the feed aligned with the front-end rolling 7-day window.
            if datetime.now(tz=timezone.utc) - dt > timedelta(days=7):
                continue
            new_items.append({
                "date": date_str,
                "company": extract_company(p["title"]),
                "title": display_title(p["title"]),
                "source_name": src["name"],
                "category": "泛具身产业链" if level == "泛具身产业链" else categorize(p["title"]),
                "url": p["url"],
            })
            added += 1
        source_stats.append({
            "name": src["name"],
            "type": src["type"],
            "fetched": True,
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
    deduped = []
    for it in all_items:
        if not allowed_existing_item(it):
            continue
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
        level = relevance_level(it.get("title", ""))
        if not level:
            continue
        date_str, dt = normalize_date(it.get("date", ""))
        if datetime.now(tz=timezone.utc) - dt > timedelta(days=7):
            continue
        it["date"] = date_str
        it["title"] = display_title(it.get("title", ""))
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
        "items": deduped,
    }
    save_data(data)
    print(f"Updated {DATA_PATH}: {len(new_items)} new, {len(deduped)} total.")


if __name__ == "__main__":
    main()
