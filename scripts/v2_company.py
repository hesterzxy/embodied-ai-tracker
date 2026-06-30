#!/usr/bin/env python3
"""Manage companies in the isolated V2 matrix.

Adds are intentionally conservative: if the shared news library contains
source-backed signals for a company, V2 writes a first-pass research column.
Otherwise it keeps the company as a pending candidate.
"""
import argparse
import json
import os
import re
from urllib.error import URLError, HTTPError
from urllib.request import Request, urlopen
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

BULLET_MAX_CHARS = 24
SUMMARY_MAX_CHARS = 10

ROW_STYLE_DEFAULTS = {
    "核心差异化": "差异明确",
    "技术选择": "路线清晰",
    "目标场景": "场景聚焦",
    "硬件能力": "硬件成型",
    "大脑自研": "大脑待验",
    "数据策略": "数据待验",
    "实测能力": "实测待验",
    "量产进度": "进度待验",
    "可靠性": "可靠待验",
    "价格/成本": "价格待明",
    "真实订单": "订单待核",
    "标杆客户": "客户待核",
    "商业模式": "模式待验",
    "创始团队": "团队待补",
    "融资估值": "资本待明",
    "股东/生态资源": "生态待明",
}

WEAK_SUMMARIES = {"待研判", "新闻待研判", "资料待补充", "暂无公开数据"}


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


def normalize_chat_url(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/v1"):
        return url + "/chat/completions"
    if not url.endswith("/chat/completions"):
        return url + "/v1/chat/completions"
    return url


def llm_config():
    aicodewith_key = os.getenv("AICODEWITH_API_KEY") or ""
    if aicodewith_key:
        return {
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
    if qwen_key:
        return {
            "api_key": qwen_key,
            "api_url": normalize_chat_url(os.getenv("QWEN_API_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
            "model": os.getenv("QWEN_MODEL") or "qwen-plus",
        }
    return {"api_key": "", "api_url": "", "model": ""}


def call_llm_json(system_prompt, user_prompt, max_tokens=7000):
    cfg = llm_config()
    if not cfg["api_key"] or not cfg["api_url"] or not cfg["model"]:
        print("V2 LLM skipped: missing API key, base URL, or model")
        return None
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    req = Request(
        cfg["api_url"],
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Content-Type": "application/json",
            "User-Agent": "embodied-ai-tracker-v2",
        },
    )
    try:
        with urlopen(req, timeout=80) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return json.loads(content)
    except (HTTPError, URLError, TimeoutError, OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        print(f"V2 LLM failed: {type(exc).__name__}: {exc}")
        return None


def make_cell(summary, bullets, sources=None, kind="evidence", confidence="medium", updated_recent=False, note=""):
    fallback_sources = sources or [{"name": "待核验", "url": "#", "evidence": ""}]
    return {
        "summary": summary[:SUMMARY_MAX_CHARS],
        "bullets": [
            {"text": text, "sources": bullet_sources or fallback_sources}
            for text, bullet_sources in bullets
        ],
        "kind": kind,
        "updated_recent": updated_recent,
        "confidence": confidence,
        "note": note,
    }


def concise_text(text, limit=BULLET_MAX_CHARS):
    text = str(text or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"([\u4e00-\u9fff])\s+([\u4e00-\u9fff])", r"\1\2", text)
    text = re.sub(r"^(IT之家|36氪|量子位|据.*?消息|.*?月.*?日消息|.*?下午消息)[，,：: ]*", "", text)
    text = re.sub(r"^(公开资料|官网|优必选官网|公司简介|新闻|报道称|介绍|称)[，,：: ]*", "", text)
    text = re.sub(r"^(本次|其中|据介绍|数据显示)[，,：: ]*", "", text)
    text = text.replace("正式推出旗下", "推出").replace("公开展示了", "展示")
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in ["，", "；", "、", "。", ",", ";"]:
        pos = cut.rfind(sep)
        if pos >= 8:
            return cut[:pos]
    return cut


def style_cell(row_label, cell):
    if not isinstance(cell, dict):
        return unknown_cell("", row_label)
    summary = str(cell.get("summary") or "").strip()
    if summary in WEAK_SUMMARIES or len(summary) > SUMMARY_MAX_CHARS:
        summary = ROW_STYLE_DEFAULTS.get(row_label, "待核验") if summary in WEAK_SUMMARIES else summary[:SUMMARY_MAX_CHARS]
    bullets = []
    for bullet in cell.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        text = concise_text(bullet.get("text"))
        if not text:
            continue
        bullets.append({
            "text": text,
            "sources": bullet.get("sources") or [{"name": "待核验", "url": "#", "evidence": ""}],
        })
        if len(bullets) >= 3:
            break
    if not bullets:
        bullets = [{"text": "公开信息不足", "sources": [{"name": "待核验", "url": "#", "evidence": ""}]}]
    cell = dict(cell)
    cell["summary"] = summary
    cell["bullets"] = bullets
    return cell


def style_profile(profile):
    if not profile:
        return None
    cells = profile.get("cells") or {}
    for label in ROW_LABELS:
        if label in cells:
            cells[label] = style_cell(label, cells[label])
    profile["cells"] = cells
    reason = str(profile.get("reason") or "").strip()
    if len(reason) > 28:
        profile["reason"] = reason[:28]
    return profile


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

    return style_profile({
        "reason": "工业集群落地 · TacForeSight接触预测",
        "cells": cells,
    })


def build_generic_profile(company_name, hits):
    return build_llm_profile(company_name, hits) or build_evidence_profile(company_name, hits)


def hit_blob(item):
    return " ".join(str(item.get(key, "")) for key in ["title", "summary", "category", "source_name", "url"])


def hit_matches(item, pattern):
    return re.search(pattern, hit_blob(item), re.I) is not None


def first_hit(hits, pattern):
    return next((item for item in hits if hit_matches(item, pattern)), None)


def best_hit(hits, pattern, boosts):
    candidates = [item for item in hits if hit_matches(item, pattern)]
    if not candidates:
        return None
    def score(item):
        text = hit_blob(item)
        total = 0
        for boost_pattern, weight in boosts:
            if re.search(boost_pattern, text, re.I):
                total += weight
        return total
    return max(candidates, key=score)


def short_fact(item, fallback):
    text = hit_blob(item)
    title = str(item.get("title") or "")
    url = str(item.get("url") or "")
    patterns = [
        (r"1\.1\s*万|1.1万|11000|超\s*1\.1\s*万", "1.1万预售订单"),
        (r"88个自由度|88\s*个", "88自由度U1"),
        (r"U1\s*(Ultra|Pro|Lite)?|优世界", "U1消费级人形"),
        (r"Walker\s*S2", "Walker S2工业版"),
        (r"Walker\s*S1", "Walker S1入厂"),
        (r"Walker\s*S\b", "Walker S工业版"),
        (r"Walker\s*C1?", "Walker C商用版"),
        (r"Cruzr\s*Y1", "Cruzr Y1轮式人形"),
        (r"自主换电|24/7|连续作业", "自主换电/连续作业"),
        (r"多模态|VSLAM|学习型运动控制", "多模态+VSLAM"),
        (r"具身智能交互大模型|具身智能", "具身智能模型"),
        (r"全栈|全栈式", "全栈技术能力"),
        (r"汽车|车厂|工厂|产线|工业制造", "工业/车厂场景"),
        (r"世博|中国馆|导览", "世博导览场景"),
        (r"家庭|陪伴|消费级", "家庭陪伴场景"),
        (r"创始人|CEO|周剑", "周剑创始团队"),
        (r"发布|推出|首发|亮相", "产品发布节点"),
        (r"量产|交付|部署", "量产交付信号"),
    ]
    for pattern, label in patterns:
        if re.search(pattern, text, re.I):
            return label
    if "ubtrobot.com" in url:
        return concise_text(title or fallback, limit=BULLET_MAX_CHARS)
    return concise_text(fallback or title, limit=BULLET_MAX_CHARS)


def evidence_bullet(item, fallback):
    if not item:
        return None
    return (short_fact(item, fallback), [source_from_item(item)])


def compact_bullets(*entries):
    bullets = []
    seen = set()
    for entry in entries:
        if not entry:
            continue
        text, sources = entry
        key = text
        if not text or key in seen:
            continue
        seen.add(key)
        bullets.append((text, sources))
        if len(bullets) >= 3:
            break
    return bullets


def fallback_bullet(company_name, item, text):
    if item:
        return (text, [source_from_item(item)])
    return (f"{company_name}{text}", [{"name": "公开来源待补", "url": "#", "evidence": ""}])


def enough_profile_evidence(hits):
    urls = {item.get("url") for item in hits if item.get("url")}
    source_names = {item.get("source_name") for item in hits if item.get("source_name")}
    return len(urls) >= 3 and len(source_names) >= 2


def recent_action(item):
    if not item:
        return False
    text = hit_blob(item)
    return bool(re.search(r"发布|推出|亮相|预售|订单|交付|量产|部署|融资|签约|客户", text, re.I))


def build_evidence_profile(company_name, hits):
    if not enough_profile_evidence(hits):
        return None

    product = best_hit(hits, r"1\.1\s*万|1.1万|11000|U1|Walker|产品|首发|发布|推出|产品系列|人形机器人", [
        (r"1\.1\s*万|1.1万|11000|订单", 5),
        (r"U1|Walker", 3),
        (r"官网|ubtrobot|IT之家|36氪", 1),
    ])
    industrial = best_hit(hits, r"工业|工厂|产线|制造|汽车|车厂|Walker\s*S|流水线", [
        (r"Walker\s*S2|Walker\s*S1|Walker\s*S", 5),
        (r"工业|工厂|车厂|产线|制造", 3),
        (r"官网|ubtrobot", 1),
    ])
    commercial = best_hit(hits, r"商用|服务|导览|世博|中国馆|Walker\s*C", [
        (r"Walker\s*C1?|世博|中国馆|导览", 4),
        (r"商用|服务", 2),
    ])
    home = best_hit(hits, r"家庭|陪伴|消费级|优世界|UWORLD|U1", [
        (r"U1|优世界|UWORLD", 4),
        (r"家庭|陪伴|消费级", 2),
    ])
    tech = first_hit(hits, r"具身智能|多模态|VSLAM|大模型|学习型|运动控制|自主换电|24/7|全栈")
    order = best_hit(hits, r"1\.1\s*万|1.1万|11000|订单|预售|交付|量产|下线|部署", [
        (r"1\.1\s*万|1.1万|11000", 8),
        (r"订单|预售", 5),
        (r"交付|量产|部署", 3),
        (r"IT之家|36氪|官网|ubtrobot", 1),
    ])
    customer = first_hit(hits, r"客户|车厂|工厂|世博|中国馆|导览|入职")
    team = first_hit(hits, r"创始人|CEO|周剑|团队")
    finance = first_hit(hits, r"融资|估值|上市|港股|IPO|投资")
    official = first_hit(hits, r"官网|company-profile|/products/|ubtrobot|公司简介")
    reference = product or official or hits[0]

    core_summary = "工业人形" if industrial else "人形矩阵"
    tech_summary = "具身模型" if tech else "技术栈"
    scene_summary = "多场景" if sum(bool(x) for x in [industrial, commercial, home]) >= 2 else ("工业场景" if industrial else "服务场景")
    hardware_summary = "Walker矩阵" if product and re.search(r"Walker", hit_blob(product), re.I) else "人形本体"
    progress_summary = "预售订单" if order and re.search(r"预售|订单|1\.1|11000", hit_blob(order), re.I) else ("量产交付" if order else "进度待跟")
    customer_summary = "车厂/展馆" if customer and re.search(r"车厂|世博|中国馆", hit_blob(customer)) else "客户待核"

    cells = {
        "核心差异化": make_cell(
            core_summary,
            compact_bullets(
                evidence_bullet(industrial or product, "人形机器人产品与工业场景同步推进"),
                evidence_bullet(tech, "公开资料披露具身智能相关技术栈"),
                evidence_bullet(order or customer, "近期公开信息出现订单、预售或部署信号"),
            ),
            kind="synthesis",
            confidence="medium",
            note="由多条公开来源自动归纳，未用输入证据外信息。",
        ),
        "技术选择": make_cell(
            tech_summary,
            compact_bullets(
                evidence_bullet(tech, "公开资料披露具身智能/多模态/运动控制能力"),
                evidence_bullet(industrial, "工业场景强调产线作业能力"),
                evidence_bullet(product, "产品页披露人形机器人能力边界"),
            ),
            confidence="medium" if tech else "low",
        ),
        "目标场景": make_cell(
            scene_summary,
            compact_bullets(
                evidence_bullet(industrial, "面向工业制造或工厂流水线"),
                evidence_bullet(commercial, "面向商用服务或导览场景"),
                evidence_bullet(home, "面向家庭陪伴或消费级场景"),
            ) or compact_bullets(evidence_bullet(reference, "公开资料披露机器人目标场景")),
            confidence="medium",
        ),
        "硬件能力": make_cell(
            hardware_summary,
            compact_bullets(
                evidence_bullet(product, "产品页或新闻披露人形机器人产品"),
                evidence_bullet(industrial, "工业版本面向产线同步作业"),
                evidence_bullet(tech, "公开资料披露控制、感知或连续作业能力"),
            ),
            confidence="medium",
        ),
        "大脑自研": make_cell(
            tech_summary,
            compact_bullets(
                evidence_bullet(tech, "公开资料提到具身智能、多模态规划或运动控制"),
                evidence_bullet(official, "官网资料披露全栈或自研能力"),
                fallback_bullet(company_name, reference, "大脑能力仍需跟踪独立评测"),
            ),
            confidence="low" if not tech else "medium",
            note="只保留公开资料能支撑的能力描述。",
        ),
        "数据策略": make_cell(
            "场景闭环",
            compact_bullets(
                evidence_bullet(industrial, "工业/工厂场景可形成真实任务闭环"),
                evidence_bullet(customer, "公开资料提到入厂、导览或客户场景"),
                fallback_bullet(company_name, reference, "训练数据规模和采集频率未披露"),
            ),
            confidence="low",
            note="数据规模未公开，当前只确认场景来源。",
        ),
        "实测能力": make_cell(
            "公开演示",
            compact_bullets(
                evidence_bullet(industrial, "公开资料披露产线或工厂作业能力"),
                evidence_bullet(commercial, "公开资料披露商用服务/导览能力"),
                evidence_bullet(product, "产品发布或官网展示本体能力"),
            ),
            confidence="medium" if industrial or commercial else "low",
        ),
        "量产进度": make_cell(
            progress_summary,
            compact_bullets(
                evidence_bullet(order, "近期公开信息披露预售、订单、交付或量产节点"),
                evidence_bullet(product, "产品线已公开发布或展示"),
                fallback_bullet(company_name, reference, "最终交付节奏仍需继续跟踪"),
            ),
            confidence="medium",
            updated_recent=recent_action(order),
        ),
        "可靠性": make_cell(
            "指标待披露",
            compact_bullets(
                evidence_bullet(tech, "公开资料披露连续作业、换电或控制能力"),
                evidence_bullet(industrial, "工业场景对稳定作业提出要求"),
                fallback_bullet(company_name, reference, "故障率、MTBF和验收周期未见充分公开披露"),
            ),
            confidence="low",
            updated_recent=False,
        ),
        "价格/成本": make_cell(
            "价格待披露",
            compact_bullets(
                evidence_bullet(order, "公开新闻披露预售或订单信号但价格需继续核验"),
                fallback_bullet(company_name, reference, "单机价格、交付口径和服务费结构未充分公开"),
                evidence_bullet(product, "产品线信息可用于后续价格跟踪"),
            ),
            confidence="low",
            updated_recent=False,
        ),
        "真实订单": make_cell(
            "预售订单" if order else "订单待核",
            compact_bullets(
                evidence_bullet(order, "近期公开信息出现订单、预售或交付线索"),
                evidence_bullet(customer, "公开资料披露客户或部署场景"),
                fallback_bullet(company_name, reference, "合同金额、回款和最终交付数仍需核验"),
            ),
            confidence="medium" if order else "low",
            updated_recent=recent_action(order),
        ),
        "标杆客户": make_cell(
            customer_summary,
            compact_bullets(
                evidence_bullet(customer, "公开资料披露车厂、工厂、展馆或导览场景"),
                evidence_bullet(industrial, "工业场景具备潜在标杆客户线索"),
                fallback_bullet(company_name, reference, "客户名单和验收口径需继续跟踪"),
            ),
            confidence="low" if not customer else "medium",
        ),
        "商业模式": make_cell(
            "产品销售",
            compact_bullets(
                evidence_bullet(product, "公开产品矩阵支撑硬件销售线索"),
                evidence_bullet(order, "预售/订单信息支撑商业化进展"),
                evidence_bullet(industrial or commercial or home, "多场景布局对应不同交付模式"),
            ),
            confidence="medium",
        ),
        "创始团队": make_cell(
            "周剑团队" if team and "周剑" in hit_blob(team) else "团队待补",
            compact_bullets(
                evidence_bullet(team, "公开新闻披露创始人或管理层观点"),
                evidence_bullet(official, "官网资料可继续补充团队背景"),
                fallback_bullet(company_name, reference, "核心技术团队履历仍需更多公开材料"),
            ),
            confidence="low" if not team else "medium",
            updated_recent=False,
        ),
        "融资估值": make_cell(
            "未见新融资",
            compact_bullets(
                evidence_bullet(finance, "公开资料出现融资、上市或估值信息"),
                fallback_bullet(company_name, reference, "本次证据包未形成新的融资估值变化"),
                fallback_bullet(company_name, reference, "估值、股价和财务口径应单独跟踪"),
            ),
            confidence="low",
            updated_recent=False,
        ),
        "股东/生态资源": make_cell(
            "产业生态",
            compact_bullets(
                evidence_bullet(industrial, "工业制造生态提供应用场景"),
                evidence_bullet(customer, "公开客户/展馆/工厂线索体现生态资源"),
                evidence_bullet(official, "官网资料披露产品与场景布局"),
            ),
            confidence="medium" if industrial or customer else "low",
        ),
    }

    concrete = sum(1 for cell in cells.values() if cell.get("summary") != "待核验")
    real_urls = {
        src.get("url")
        for cell in cells.values()
        for bullet in cell.get("bullets", [])
        for src in bullet.get("sources", [])
        if src.get("url") and src.get("url") != "#"
    }
    if concrete < 10 or len(real_urls) < 3:
        return None

    return style_profile({
        "reason": f"{core_summary} · {progress_summary}",
        "cells": cells,
    })


def evidence_pack(company_name, hits, limit=12):
    rows = []
    for idx, item in enumerate(hits[:limit], 1):
        rows.append({
            "id": idx,
            "date": item.get("date", ""),
            "source_name": item.get("source_name", ""),
            "category": item.get("category", ""),
            "title": item.get("title", ""),
            "summary": item.get("summary", ""),
            "url": item.get("url", ""),
        })
    return rows


def llm_system_prompt():
    return (
        "你是严谨的具身智能产业研究分析师。你的任务是基于给定证据，生成竞对矩阵的一列。"
        "只能使用输入证据，不允许编造、外推或引用输入之外的来源。"
        "如果证据不足，返回 can_publish=false。"
        "表达必须像咨询竞对表：短句、名词化、可横向比较；禁止新闻摘要长句。"
        "不要输出 markdown，只输出严格 JSON。"
    )


def llm_user_prompt(company_name, hits):
    return f"""请基于下列公开新闻证据，为「{company_name}」生成 V2 竞对矩阵新增列。

维度必须覆盖以下 16 个：
{json.dumps(ROW_LABELS, ensure_ascii=False)}

证据：
{json.dumps(evidence_pack(company_name, hits), ensure_ascii=False, indent=2)}

质量要求：
1. 只有当证据足以形成可比竞对判断时，can_publish 才能为 true；否则 false。
2. 禁止使用“待研判”“新闻待研判”“资料待补充”“暂无公开数据”作为正式列 summary。
3. summary 不超过 10 个汉字，必须具体到这家公司，例如“BMW产线”“千台集群”“手部组件”，不要写“技术领先/场景明确/行业动态”。
4. 每个非 synthesis 维度必须有 2-3 条 bullet；每条 bullet 必须绑定输入证据中的 URL，且每条 bullet 不超过 24 个汉字。
5. 不能用同一条新闻硬撑所有维度。没有证据的维度可以 summary="待核验"，confidence="low"，但如果待核验维度超过 6 个，can_publish=false。
6. updated_recent 只有在该格对应近 30 天重大动作时为 true，例如融资、订单、量产、发布、部署、重大论文/产品节点；普通背景信息和路线归纳必须 false。
7. 蓝色高亮不能超过 3 个维度。
8. 如果只有单一信源或单一事件，原则上 can_publish=false，除非该事件本身足够重大且公司已有清晰公开定位。
9. bullet 写法参考“工业制造/汽车产线”“G0双系统VLA框架”“产品价格未公开”，不要写“某媒体某月某日消息...”。

输出 JSON 格式：
{{
  "can_publish": true,
  "company": "{company_name}",
  "reason": "一句话标签，用 · 分隔，最多 24 字",
  "notes": "简短质量说明",
  "cells": {{
    "核心差异化": {{
      "summary": "10字内",
      "kind": "synthesis",
      "updated_recent": false,
      "confidence": "high|medium|low",
      "note": "",
      "bullets": [
        {{"text":"事实或判断", "sources":[{{"name":"来源名 日期", "url":"输入证据URL", "evidence":"短证据"}}]}}
      ]
    }}
  }}
}}"""


def normalize_llm_source(src, allowed_urls):
    if not isinstance(src, dict):
        return None
    url = src.get("url") or ""
    if url not in allowed_urls:
        return None
    return {
        "name": str(src.get("name") or "公开来源")[:40],
        "url": url,
        "evidence": str(src.get("evidence") or "")[:120],
    }


def normalize_llm_cell(label, raw, allowed_urls):
    if not isinstance(raw, dict):
        return None
    summary = str(raw.get("summary") or "").strip()[:10]
    if not summary or summary in {"待研判", "新闻待研判", "资料待补充"}:
        return None
    bullets = []
    for bullet in raw.get("bullets") or []:
        if not isinstance(bullet, dict):
            continue
        text = str(bullet.get("text") or "").strip()[:80]
        sources = [normalize_llm_source(src, allowed_urls) for src in (bullet.get("sources") or [])]
        sources = [src for src in sources if src]
        if text and (sources or label == "核心差异化"):
            bullets.append({"text": text, "sources": sources or [{"name": "战略归纳", "url": "#", "evidence": ""}]})
    if len(bullets) < 2 and summary != "待核验":
        return None
    confidence = raw.get("confidence") if raw.get("confidence") in {"high", "medium", "low"} else "low"
    return {
        "summary": summary,
        "bullets": bullets[:3] if bullets else [{"text": "暂无可靠公开数据", "sources": [{"name": "待核验", "url": "#", "evidence": ""}]}],
        "kind": "synthesis" if label == "核心差异化" else "evidence",
        "updated_recent": raw.get("updated_recent") is True,
        "confidence": confidence,
        "note": str(raw.get("note") or "")[:120],
    }


def validate_llm_profile(profile, company_name, hits):
    if not isinstance(profile, dict) or profile.get("can_publish") is not True:
        return None
    allowed_urls = {item.get("url") for item in hits if item.get("url")}
    source_names = {item.get("source_name") for item in hits if item.get("source_name")}
    if len(allowed_urls) < 2:
        return None
    if len(source_names) < 2:
        return None
    raw_cells = profile.get("cells")
    if not isinstance(raw_cells, dict):
        return None
    cells = {}
    recent_count = 0
    pending_count = 0
    concrete_count = 0
    used_urls = set()
    url_use_count = {}
    for label in ROW_LABELS:
        cell = normalize_llm_cell(label, raw_cells.get(label), allowed_urls)
        if not cell:
            cell = unknown_cell(company_name, label)
        if cell["summary"] == "待核验":
            pending_count += 1
        else:
            concrete_count += 1
        if cell.get("updated_recent"):
            recent_count += 1
        for bullet in cell.get("bullets", []):
            for src in bullet.get("sources", []):
                if src.get("url") and src.get("url") != "#":
                    used_urls.add(src["url"])
                    url_use_count[src["url"]] = url_use_count.get(src["url"], 0) + 1
        cells[label] = cell
    if pending_count > 6 or concrete_count < 8 or len(used_urls) < 2:
        return None
    if url_use_count and max(url_use_count.values()) > 10:
        return None
    if recent_count > 3:
        for label in ROW_LABELS:
            cells[label]["updated_recent"] = False
    reason = str(profile.get("reason") or profile.get("notes") or "V2 API生成").strip()[:40]
    return style_profile({"reason": reason, "cells": cells})


def build_llm_profile(company_name, hits):
    if len(hits) < 2:
        return None
    profile = call_llm_json(llm_system_prompt(), llm_user_prompt(company_name, hits))
    return validate_llm_profile(profile, company_name, hits)


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


def is_low_quality_column(table, company_idx):
    bad_summaries = {"待研判", "新闻待研判", "资料待补充"}
    bad_count = 0
    low_count = 0
    recent_bad = 0
    for group in table.get("groups", []):
        for row in group.get("rows", []):
            cells = row.get("cells", [])
            cell = cells[company_idx] if company_idx < len(cells) else {}
            if not isinstance(cell, dict):
                continue
            summary = cell.get("summary")
            if summary in bad_summaries:
                bad_count += 1
                if cell.get("updated_recent"):
                    recent_bad += 1
            if cell.get("confidence") == "low":
                low_count += 1
    return bad_count > 0 or recent_bad > 0 or low_count >= 14


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
        if is_low_quality_column(table, idx):
            remove_company(table, company_name, remove_research=False)
            idx = -1
            companies = table.setdefault("companies", [])
        else:
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


def remove_company(table, company_name, remove_research=True):
    company_name = canonical_company_name(company_name)
    removed_research = remove_v2_research_company(company_name) if remove_research else False
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
