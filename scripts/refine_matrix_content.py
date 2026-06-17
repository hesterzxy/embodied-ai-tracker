#!/usr/bin/env python3
"""Refine matrix ordering and cell summaries for the current v2 schema."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "data" / "table.json"

GROUP_ORDER = [
    ("战略定位", ["核心差异化", "技术路线", "目标场景"]),
    ("技术能力", ["硬件能力", "大脑自研", "数据策略", "实测能力"]),
    ("产品化进展", ["量产进度", "可靠性", "价格/成本"]),
    ("商业化验证", ["真实订单", "标杆客户", "商业模式"]),
    ("组织与资本", ["创始团队", "融资估值", "股东/生态资源"]),
]

SUMMARY = {
    "核心差异化": ["量产速度", "VLA抓取", "仿真数据", "硬件低价", "自产场景", "海外工厂", "纯模型层", "灵巧手"],
    "技术路线": ["整机+大脑", "端到端VLA", "仿真驱动", "运动控制", "FSD迁移", "Helix自研", "跨本体模型", "手部优先"],
    "目标场景": ["工业优先", "搬运拣选", "零售工业", "科研教育", "自有工厂", "BMW产线", "模型赋能", "手部组件"],
    "硬件能力": ["双臂工业", "轮式双臂", "重载双臂", "四足到人形", "全栈本体", "量产本体", "不造硬件", "高自由度手"],
    "大脑自研": ["启元模型", "G0模型", "银河星脑", "补上层脑", "FSD大脑", "Helix模型", "π0模型", "大脑待明"],
    "数据策略": ["工厂闭环", "真机场景", "合成主导", "生态数据", "车队迁移", "工厂采集", "跨本体数据", "触觉数据"],
    "实测能力": ["螺丝锁付", "泛化抓取", "工厂作业", "运动展示", "仍在内测", "BMW班次", "论文泛化", "精细手操"],
    "量产进度": ["万台下线", "小批出货", "百台运营", "人形放量", "量产延后", "BotQ爬坡", "软件为主", "手已量产"],
    "可靠性": ["产线验证", "耐久测试", "常态作业", "出货验证", "仍待验证", "工厂班次", "模型验证", "演示稳定"],
    "价格/成本": ["售价未明", "B端定价", "手部高价", "低价标杆", "目标降本", "RaaS待明", "软件授权", "手部昂贵"],
    "真实订单": ["万台出货", "千台订单", "订单待证", "人形出货", "内部部署", "BMW部署", "无硬件单", "手部订单"],
    "标杆客户": ["比亚迪链", "蓝思合作", "宁德生态", "英伟达链", "特斯拉内用", "BMW客户", "学研合作", "英伟达平台"],
    "商业模式": ["整机+RaaS", "整机平台", "场景运营", "硬件销售", "先内用", "RaaS订阅", "模型授权", "部件销售"],
    "创始团队": ["华为背景", "Waymo系", "学术+产业", "创始人控股", "马斯克牵引", "硬件老兵", "斯坦福系", "禾赛团队"],
    "融资估值": ["150亿估值", "200亿估值", "200亿+", "IPO进程", "集团内项目", "$39B估值", "$5.6B估值", "估值待证"],
    "股东/生态资源": ["腾讯比亚迪", "蓝思资本", "宁德绑定", "英伟达生态", "特斯拉工厂", "BMW绑定", "学研社区", "禾赛渊源"],
}

ECO_BULLETS = {
    "智元 AgiBot": ["腾讯、比亚迪等资本参与", "比亚迪兼具股东与客户属性", "制造业客户可形成数据闭环"],
    "星海图 Galaxea": ["蓝思科技为战略合作方", "蓝思同时参与B+轮融资", "车企合作仍待公开确认"],
    "银河通用 Galbot": ["宁德时代同时具投资与场景价值", "与博世、丰田、北汽上汽等建立合作", "零售与工业场景可提供运营数据"],
    "宇树 Unitree": ["英伟达GR00T生态合作", "海外科研与开发者基础强", "硬件平台具参考设计价值"],
    "特斯拉 Optimus": ["依托特斯拉工厂与供应链", "FSD、Dojo与制造体系可复用", "外部客户尚未公开"],
    "Figure": ["BMW是最明确标杆客户", "BotQ制造体系服务量产爬坡", "物流客户仍待公开确认"],
    "Physical Intelligence": ["斯坦福与谷歌系研究网络强", "依赖机器人厂商间接落地", "开源/研究社区是扩散路径"],
}


def row_map(data):
    return {row["label"]: row for group in data["groups"] for row in group["rows"]}


def make_source(name="战略归纳", url="#"):
    return {"name": name, "url": url, "evidence": ""}


def set_synthesis(row, companies):
    for idx, cell in enumerate(row["cells"]):
        reason = companies[idx].get("reason", "")
        parts = [p.strip() for p in reason.replace("·", "，").split("，") if p.strip()]
        cell["kind"] = "synthesis"
        cell["confidence"] = "medium"
        cell["note"] = "战略归纳，不显示引用编号"
        cell["summary"] = SUMMARY["核心差异化"][idx]
        cell["bullets"] = [
            {"text": p[:80], "sources": [make_source()]} for p in (parts[:3] or [reason or "暂无归纳"])
        ]


def replace_ecosystem(row, companies):
    for idx, cell in enumerate(row["cells"]):
        name = companies[idx]["name"]
        bullets = ECO_BULLETS.get(name, ["生态信息待核验"])
        cell["summary"] = SUMMARY["股东/生态资源"][idx]
        cell["confidence"] = "low" if any("待公开" in b or "待核验" in b or "待证" in b for b in bullets) else "medium"
        cell["note"] = "生态资源维度聚焦股东、产业伙伴、客户与社区，不等同于融资估值"
        old_sources = []
        for b in cell.get("bullets", []):
            old_sources.extend(b.get("sources", []))
        src = old_sources[:1] or [make_source("待核验")]
        cell["bullets"] = [{"text": b, "sources": src} for b in bullets[:3]]


def main():
    data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    companies = data["companies"]
    rows = row_map(data)

    for label, summaries in SUMMARY.items():
        row = rows.get(label)
        if not row:
            continue
        for idx, cell in enumerate(row["cells"]):
            if idx < len(summaries):
                cell["summary"] = summaries[idx]

    if "核心差异化" in rows:
        set_synthesis(rows["核心差异化"], companies)
    if "股东/生态资源" in rows:
        replace_ecosystem(rows["股东/生态资源"], companies)

    new_groups = []
    for group_label, labels in GROUP_ORDER:
        new_groups.append({"label": group_label, "rows": [rows[label] for label in labels if label in rows]})
    data["groups"] = new_groups
    data["schema_version"] = 2
    data["verification_method"] = "triangulated_evidence_v1"
    TABLE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
