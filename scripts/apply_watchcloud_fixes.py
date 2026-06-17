#!/usr/bin/env python3
"""Apply targeted fact wording fixes from the WatchCloud review."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "data" / "table.json"


def company_index(data, needle):
    for idx, company in enumerate(data["companies"]):
        if needle in company["name"]:
            return idx
    raise KeyError(needle)


def rows_by_label(data):
    return {row["label"]: row for group in data["groups"] for row in group["rows"]}


def source(name="公开来源待核验", url="#"):
    return {"name": name, "url": url, "evidence": ""}


def reuse_sources(cell, fallback="公开来源待核验"):
    sources = []
    for bullet in cell.get("bullets", []):
        sources.extend(bullet.get("sources", []))
    return sources[:1] or [source(fallback)]


def set_cell(rows, label, idx, summary=None, bullets=None, confidence=None, note=None, sources=None):
    cell = rows[label]["cells"][idx]
    if summary is not None:
        cell["summary"] = summary
    if bullets is not None:
        src = sources or reuse_sources(cell)
        cell["bullets"] = [{"text": text, "sources": src} for text in bullets]
    if confidence is not None:
        cell["confidence"] = confidence
    if note is not None:
        cell["note"] = note
    return cell


def replace_text(rows, label, idx, old, new):
    for bullet in rows[label]["cells"][idx].get("bullets", []):
        if bullet.get("text") == old:
            bullet["text"] = new


def main():
    data = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    rows = rows_by_label(data)

    agibot = company_index(data, "智元")
    galbot = company_index(data, "银河通用")
    unitree = company_index(data, "宇树")
    tesla = company_index(data, "特斯拉")
    figure = company_index(data, "Figure")
    pi = company_index(data, "Physical Intelligence")

    data["companies"][unitree]["reason"] = "硬件成本标杆 · 人形出货口径需区分"
    data["companies"][tesla]["reason"] = "全栈天花板 · 感知/算力体系复用"
    data["companies"][pi]["reason"] = "纯模型路线 · π0系列跨本体"

    set_cell(
        rows,
        "核心差异化",
        unitree,
        summary="硬件低价",
        bullets=["硬件成本标杆", "人形出货为自报口径", "第三方口径与智元排名有差异"],
        note="战略归纳，不显示引用编号；出货量口径存在公司自报与第三方统计差异",
    )
    set_cell(
        rows,
        "量产进度",
        unitree,
        summary="口径分歧",
        bullets=["四足全球领先", "宇树官宣人形2025出货5500+台", "Omdia口径约4200台、列第二"],
        confidence="medium",
        note="宇树官方口径与Omdia第三方统计存在差异；避免直接写人形全球第一",
    )
    set_cell(
        rows,
        "真实订单",
        unitree,
        summary="自报出货",
        bullets=["宇树官宣人形2025出货5500+台", "Omdia口径约4200台、列第二", "四足销量另算"],
        confidence="medium",
        note="出货量按口径拆分展示，不直接合并为全球第一",
    )
    set_cell(
        rows,
        "创始团队",
        unitree,
        summary="创始人控制",
        bullets=["王兴兴任创始人/CEO/CTO", "直接持股23.82%", "通过AB股控制表决权68.78%"],
        confidence="medium",
        note="股权采用招股书常见直接持股与表决权口径",
    )

    set_cell(
        rows,
        "大脑自研",
        pi,
        summary="π0系列",
        bullets=["π0/π0.5/π0.7 VLA路线", "世界模型与行为-动作模型", "核心自研能力"],
        confidence="medium",
        note="不展示非正式代际写法，避免与π0系列主线混淆",
        sources=[source("Physical Intelligence π0.5", "https://www.physicalintelligence.company/blog/pi05")],
    )
    set_cell(
        rows,
        "创始团队",
        pi,
        summary="学术+谷歌",
        bullets=["Karol Hausman任CEO，前Google DeepMind", "Chelsea Finn为斯坦福教授", "Sergey Levine为UC Berkeley教授"],
        confidence="medium",
        note="创始团队按公开身份拆分为斯坦福/伯克利+Google DeepMind系",
        sources=[source("Wired / PI创始团队", "https://www.wired.com/story/physical-intelligence-ai-robotics-startup")],
    )
    set_cell(
        rows,
        "股东/生态资源",
        pi,
        summary="学研社区",
        bullets=["斯坦福/UC Berkeley学研网络强", "Google DeepMind系经验明显", "依赖机器人厂商间接落地"],
        confidence="medium",
        note="生态资源维度聚焦学研、产业伙伴、客户与社区，不等同于融资估值",
    )

    replace_text(rows, "标杆客户", galbot, "宁德时代(唯一投资具身+常态作业客户)", "宁德时代（既投资、又是常态化作业客户）")
    set_cell(
        rows,
        "实测能力",
        galbot,
        summary="工厂作业",
        bullets=["宁德时代工厂全自主作业", "公开春晚演示不纳入其手部能力判断", "精细操作能力需看自有硬件实测"],
        confidence="medium",
        note="春晚机械手供应方可能涉及外部厂商；不把该手部能力归因于银河通用",
    )
    set_cell(
        rows,
        "可靠性",
        galbot,
        summary="常态作业",
        bullets=["宁德时代常态化作业", "零售运营可观察持续运行", "春晚演示仅作曝光事件，不作为可靠性证明"],
        confidence="medium",
        note="避免把可能使用外部灵巧手的春晚演示归因为银河通用能力",
    )

    set_cell(
        rows,
        "核心差异化",
        tesla,
        summary="自产场景",
        bullets=["全栈自研体系", "自有工厂先验证", "复用感知栈/算力体系"],
        note="战略归纳，不显示引用编号；FSD相关表述限定为感知栈和算力体系复用",
    )
    set_cell(
        rows,
        "硬件能力",
        tesla,
        summary="全栈本体",
        bullets=["Optimus Gen3仍待正式规格", "Gen3手部22自由度为常见披露", "执行器数量口径未稳定，暂不写50个"],
        confidence="low",
        note="硬件规格未充分三角核验，保守展示",
    )
    set_cell(
        rows,
        "大脑自研",
        tesla,
        summary="FSD复用",
        bullets=["全自研感知/规划体系", "FSD与Dojo能力可复用", "不等同于驾驶数据直接迁移为操作数据"],
        confidence="medium",
        note="驾驶数据与机器人操作数据不同，此处限定为感知栈、算力与工程体系复用",
    )
    set_cell(
        rows,
        "数据策略",
        tesla,
        summary="工厂数据",
        bullets=["自有工厂部署采集", "复用车端感知与训练体系", "操作数据仍需机器人实机闭环"],
        confidence="medium",
        note="驾驶数据不直接等同于操作数据",
    )
    set_cell(
        rows,
        "量产进度",
        tesla,
        summary="2026目标",
        bullets=["研发测试阶段", "公开目标多指向2026年量产", "具体月份未稳定披露"],
        confidence="low",
        note="不写2026年夏，避免过度具体",
    )
    set_cell(
        rows,
        "创始团队",
        tesla,
        summary="内部项目",
        bullets=["马斯克直接推动", "特斯拉内部团队", "Optimus未独立分拆"],
        confidence="medium",
    )

    set_cell(
        rows,
        "实测能力",
        figure,
        summary="BMW试点",
        bullets=["进入BMW Spartanburg产线试点", "公开展示以整机搬运/零件处理为主", "部署规模与班次数字未稳定披露"],
        confidence="medium",
        note="Figure官方披露班次与产量贡献；BMW未披露机器人数量或交易规模",
        sources=[source("Figure AI官网", "https://www.figure.ai/news/production-at-bmw")],
    )
    set_cell(
        rows,
        "真实订单",
        figure,
        summary="BMW试点",
        bullets=["已进入BMW量产线试点", "机器人数量与交易规模未公开", "第二客户待公开确认"],
        confidence="medium",
        note="不写数百台，避免夸大部署规模",
        sources=[source("Figure AI官网", "https://www.figure.ai/news/production-at-bmw")],
    )
    set_cell(
        rows,
        "标杆客户",
        figure,
        summary="BMW客户",
        bullets=["BMW为明确标杆客户", "Figure官方披露贡献3万+ X3生产", "机器人数量与交易规模未公开"],
        confidence="medium",
        note="车辆产量贡献为Figure官方口径，避免表述为BMW独立确认",
        sources=[source("Figure AI官网", "https://www.figure.ai/news/production-at-bmw")],
    )

    set_cell(
        rows,
        "硬件能力",
        agibot,
        summary="双臂工业",
        bullets=["远征A2双臂工业机", "关节高扭矩参数待官方规格复核", "灵犀X2轻量化版"],
        confidence="medium",
        note="512Nm具体数值暂不展示，待官方规格书或双源核验",
    )
    set_cell(
        rows,
        "量产进度",
        agibot,
        summary="万台下线",
        bullets=["官方披露万台下线", "公开报道指向2026年3月节点", "万台级产线持续爬坡"],
        confidence="medium",
        note="具体日期建议以后以官方公告/权威媒体复核",
    )

    TABLE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
