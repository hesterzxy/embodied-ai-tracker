#!/usr/bin/env python3
"""
自动化数据刷新脚本 - 三角验证具身智能公司对比数据

用法:
  python scripts/auto_update.py --only-pending    # 只处理新增公司
  python scripts/auto_update.py --all             # 刷新所有公司
  python scripts/auto_update.py --company 智元   # 刷新特定公司
  python scripts/auto_update.py --dry-run         # 只生成报告，不修改文件

需要配置的环境变量 (任选其一):
  ANTHROPIC_API_KEY   # Claude API Key (推荐)
  OPENAI_API_KEY      # GPT API Key
  QWEN_API_KEY        # 通义千问/DashScope API Key

输出:
  data/table.json            # 更新后的对比表数据
  data/verification_report.md  # 三角验证报告（供人工审核）
"""

import json
import os
import sys
import argparse
import datetime
from pathlib import Path

# ---- 配置 ----
ROOT = Path(__file__).parent.parent
TABLE_PATH = ROOT / 'data' / 'table.json'
PENDING_PATH = ROOT / 'data' / 'pending_companies.json'
REPORT_PATH = ROOT / 'data' / 'verification_report.md'

# 矩阵维度定义：保持 MECE，前端按此顺序渲染
DIMENSIONS = {
    '战略定位': ['核心差异化', '技术选择', '目标场景'],
    '技术能力': ['硬件能力', '大脑自研', '数据策略', '实测能力'],
    '产品化进展': ['量产进度', '可靠性', '价格/成本'],
    '商业化验证': ['真实订单', '标杆客户', '商业模式'],
    '组织与资本': ['创始团队', '融资估值', '股东/生态资源'],
}
ALL_DIMS = [d for group in DIMENSIONS.values() for d in group]

SYS_PROMPT = """你是一个严谨的产业研究分析师，专长是具身智能/人形机器人领域。
你的任务是搜集并验证公司信息，确保每个数据点都有公开来源支持。

关键原则:
1. 每个矩阵格子必须形成两层：summary（10个汉字以内）+ 2-3条 bullets。
2. summary 必须公司特异化，直接说明该公司在该维度的状态，例如“万台下线”“低价标杆”“BMW产线”，不要写“场景明确”“硬件见长”这类泛词。
3. 每条 bullet 只表达一个事实或判断，必须绑定能直接支撑该 bullet 的来源。
4. 「核心差异化」是战略归纳，可标 kind="synthesis"，不强制显示来源；其他维度默认 kind="evidence"。
5. 三角验证优先级：公司官网/官方公众号/发布会 > 权威媒体 > 研报/数据库/财报/招股书。
6. 关键事实（出货量、量产、订单、客户、估值、价格）需要至少 2 个独立来源一致才标 high。
7. 只有 1 个来源、来源较弱、或内容含预测/传闻/目标时，confidence 标 medium 或 low。
8. 来源冲突时不要覆盖原事实，confidence 标 low，并在 notes 写明冲突。
9. 如果没有可靠来源，明确标注「暂无公开数据」，不要猜测。
10. 中文回答，不要使用营销化表达，如“天花板”“遥遥领先”，除非 bullet 里有指标支撑。

输出格式是严格的 JSON (不要用 markdown 代码块):
{
  "company": "公司名称",
  "tagline": "一句话描述（如：整机量产最快 · 第1万台2026年3月下线）",
  "data": {
    "维度名称": {
      "summary": "10个汉字以内的小标题",
      "kind": "evidence|synthesis",
      "updated_recent": false,
      "confidence": "high|medium|low",
      "note": "低置信或冲突说明，没有则为空",
      "bullets": [
        {
          "text": "支撑summary的事实，尽量不超过24个汉字",
          "sources": [
            {
              "name": "来源名称和日期，如：36氪 2026-04",
              "url": "完整URL或#",
              "evidence": "该来源中能支持本bullet的短证据摘要"
            }
          ]
        }
      ]
    }
  },
  "confidence": "high|medium|low",
  "notes": "验证过程中的备注，如：该数据有两个来源不一致"
}"""


def load_json(path, default=None):
    """读取 JSON 文件，不存在则返回默认值"""
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 已保存 {path.name}")


def call_llm(prompt, use_anthropic=True):
    """调用 LLM API。优先使用 Anthropic Claude，备选 OpenAI。"""
    anthropic_key = os.environ.get('ANTHROPIC_API_KEY', '')
    openai_key = os.environ.get('OPENAI_API_KEY', '')
    qwen_key = os.environ.get('QWEN_API_KEY', '')

    if anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            response = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8000,
                system=SYS_PROMPT,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text if response.content else ''
        except ImportError:
            print("  ⚠️  需要安装 anthropic: pip install anthropic")
        except Exception as e:
            print(f"  ⚠️  Claude API 调用失败: {e}")

    if openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": SYS_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content or ''
        except ImportError:
            print("  ⚠️  需要安装 openai: pip install openai")
        except Exception as e:
            print(f"  ⚠️  OpenAI API 调用失败: {e}")

    if qwen_key:
        try:
            import openai
            client = openai.OpenAI(
                api_key=qwen_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
            response = client.chat.completions.create(
                model="qwen-plus",
                messages=[
                    {"role": "system", "content": SYS_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content or ''
        except ImportError:
            print("  ⚠️  需要安装 openai: pip install openai")
        except Exception as e:
            print(f"  ⚠️  Qwen API 调用失败: {e}")

    return None  # 无可用 API Key


def parse_llm_response(text, company_name):
    """解析 LLM 返回的 JSON。非常宽容的解析器。"""
    if not text:
        return None

    # 清理可能的 markdown 代码块标记
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = cleaned.strip('`')
        if cleaned.lower().startswith('json'):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试提取第一个 { 到最后一个 } 之间的内容
        first = cleaned.find('{')
        last = cleaned.rfind('}')
        if first >= 0 and last > first:
            try:
                return json.loads(cleaned[first:last+1])
            except json.JSONDecodeError:
                pass

        print(f"  ⚠️  {company_name}: LLM 输出无法解析为 JSON")
        print(f"      前200字: {cleaned[:200]}")
        return None


def normalize_source(src):
    if isinstance(src, dict):
        return {
            'name': src.get('name') or src.get('source_name') or '待核验',
            'url': src.get('url') or src.get('source_url') or '#',
            'evidence': src.get('evidence', '')
        }
    if isinstance(src, str):
        return {'name': src, 'url': src if src.startswith('http') else '#', 'evidence': ''}
    return {'name': '待核验', 'url': '#', 'evidence': ''}


def confidence_from_cell(cell):
    if not isinstance(cell, dict):
        return 'low'
    if cell.get('kind') == 'synthesis':
        return cell.get('confidence', 'medium') if cell.get('confidence') in ['high', 'medium', 'low'] else 'medium'
    text = json.dumps(cell, ensure_ascii=False)
    if any(k in text for k in ['暂无', '未公开', '传闻', '可能', '预计', '目标', '待核验']):
        return 'low'
    source_count = 0
    for b in cell.get('bullets', []):
        source_count += len([s for s in b.get('sources', []) if normalize_source(s).get('url') != '#'])
    return 'high' if source_count >= 2 else 'medium'


def normalize_cell(dim, raw):
    if not isinstance(raw, dict):
        raw = {
            'summary': '待核验',
            'confidence': 'low',
            'note': 'LLM 未按结构化格式返回',
            'bullets': [{'text': str(raw or '暂无公开数据'), 'sources': [{'name': '待核验', 'url': '#'}]}]
        }
    summary = str(raw.get('summary') or '待核验').strip()[:10]
    bullets = raw.get('bullets') or []
    if not isinstance(bullets, list):
        bullets = []
    normalized_bullets = []
    for b in bullets[:3]:
        if isinstance(b, dict):
            text = str(b.get('text') or '').strip()
            sources = [normalize_source(s) for s in b.get('sources', [])]
        else:
            text = str(b).strip()
            sources = [{'name': '待核验', 'url': '#', 'evidence': ''}]
        if text:
            normalized_bullets.append({'text': text[:80], 'sources': sources or [{'name': '待核验', 'url': '#', 'evidence': ''}]})
    while len(normalized_bullets) < 2:
        normalized_bullets.append({'text': '暂无可靠公开数据', 'sources': [{'name': '待核验', 'url': '#', 'evidence': ''}]})
    cell = {
        'summary': summary,
        'bullets': normalized_bullets[:3],
        'kind': raw.get('kind') if raw.get('kind') in ['evidence', 'synthesis'] else ('synthesis' if dim == '核心差异化' else 'evidence'),
        'updated_recent': raw.get('updated_recent') is True,
        'confidence': raw.get('confidence') if raw.get('confidence') in ['high', 'medium', 'low'] else 'medium',
        'note': raw.get('note', '')
    }
    auto_conf = confidence_from_cell(cell)
    if auto_conf == 'low':
        cell['confidence'] = 'low'
        if not cell['note']:
            cell['note'] = '来源不足或包含预测/传闻，待三角核验'
    return cell


def extract_existing_company_data(existing_table, company_name):
    companies = existing_table.get('companies', [])
    idx = next((i for i, c in enumerate(companies) if c.get('name') == company_name), None)
    if idx is None:
        return None
    data = {}
    for group in existing_table.get('groups', []):
        for row in group.get('rows', []):
            cells = row.get('cells', [])
            if idx < len(cells):
                data[row.get('label')] = cells[idx]
    return data


def build_prompt_for_company(company_name, existing_data=None, is_new=False):
    """构建针对某家公司的验证提示词"""
    current_info = ''
    if existing_data:
        current_info = f"""
当前已有数据（供参考，请验证或更新）:
{json.dumps(existing_data, ensure_ascii=False, indent=2)}

请验证上述数据是否仍然准确。如有更新请替换，如确认无误请保留原数据。
"""

    return f"""请对「{company_name}」进行全面的信息搜集和三角验证，覆盖以下 {len(ALL_DIMS)} 个维度:

{json.dumps(ALL_DIMS, ensure_ascii=False, indent=2)}

{'这是一家新加入的公司，请特别关注其基本信息。' if is_new else ''}

产出 harness:
1. 每个维度输出 summary + bullets，summary 不超过10个汉字。
2. summary 必须具体到该公司，避免“场景明确/硬件见长/模型驱动”等泛化标题。
3. 每个维度必须有2-3条 bullets，每条 bullet 是一个可核验的事实或判断。
4. 除「核心差异化」外，每条 bullet 必须带 sources；source 必须能直接支持该 bullet，不要用“量产新闻”支持“技术选择”。
5. 「核心差异化」用 kind="synthesis"，可以基于所有维度归纳，不显示引用编号。
6. 出货量、订单、估值、价格、客户、量产进度等关键事实，至少两个独立来源一致才标 high。
7. 只有单一来源、来源较弱、或内容是计划/传闻/目标时，标 medium 或 low，并写 note。
8. updated_recent 只有在近30天新闻使该格子的事实或判断发生实质变化时才写 true；仅因来源日期近30天、但内容是既有路线，不算更新。
9. 不要写空泛结论；如果要写“领先”，必须在 bullet 中给出具体指标。
10. 没有可靠资料时 summary 写“待核验”，bullet 写“暂无可靠公开数据”，confidence 写 low。
11. 全表引用必须做可访问性核查：不要输出打不开、403/404/406、页面不存在、登录墙、聚合页、搜索页、或与 bullet 不严格匹配的 URL。找不到稳定链接时，先改弱/删除该 bullet，不要硬贴来源。
12. 优先使用公司官网、招股书/公告、论文、权威媒体、投资方公告；雪球、转载号、综合资讯站只可作辅助来源，不作为唯一来源支撑关键事实。
13. 最新动态更新后，本周周报必须基于同一份 data/news.json 同步刷新；周报摘要写 2-3 条“趋势：证据和含义”，不要只罗列新闻标题。

{current_info}

请直接输出严格的 JSON 格式。"""


def process_company(company_name, existing_company=None, is_new=False):
    """处理单家公司：调用 LLM → 解析 → 返回结构化数据"""
    print(f"\n  → 正在验证: {company_name}")

    existing_data = existing_company

    prompt = build_prompt_for_company(company_name, existing_data, is_new)
    response = call_llm(prompt)

    if response is None:
        print(f"    ⚠️  无 API Key 或 API 调用失败，跳过 {company_name}")
        return None

    parsed = parse_llm_response(response, company_name)
    if not parsed:
        return None

    # 验证返回的数据格式
    if 'data' not in parsed:
        print(f"    ⚠️  返回格式缺少 data 字段")
        return None

    # 确保所有维度都有结构化数据
    for dim in ALL_DIMS:
        if dim not in parsed['data']:
            parsed['data'][dim] = {
                'summary': '待核验',
                'confidence': 'low',
                'note': 'LLM 未返回该维度',
                'bullets': [{'text': '暂无可靠公开数据', 'sources': [{'name': '待核验', 'url': '#'}]}]
            }
        parsed['data'][dim] = normalize_cell(dim, parsed['data'][dim])

    print(f"    ✓ 已获取 {len(parsed['data'])} 个维度数据")
    print(f"    置信度: {parsed.get('confidence', 'unknown')}")
    if parsed.get('notes'):
        print(f"    备注: {parsed['notes'][:100]}")

    return parsed


def build_placeholder_company(company_name, note):
    """Create a visible low-confidence placeholder when a new company cannot be verified yet."""
    data = {}
    for dim in ALL_DIMS:
        data[dim] = {
            'summary': '待核验',
            'kind': 'synthesis' if dim == '核心差异化' else 'evidence',
            'updated_recent': False,
            'confidence': 'low',
            'note': note,
            'bullets': [
                {
                    'text': '自动核验暂未完成',
                    'sources': [{'name': '待核验', 'url': '#', 'evidence': ''}]
                },
                {
                    'text': '等待公开来源补充',
                    'sources': [{'name': '待核验', 'url': '#', 'evidence': ''}]
                }
            ]
        }
    return {
        'company': company_name,
        'tagline': '资料待核验 · 已进入更新队列',
        'data': data,
        'confidence': 'low',
        'notes': note
    }


def restore_company_from_table(old_co, idx, old_groups):
    """Convert one company column from table.json back to company-oriented data."""
    cd = {
        'company': old_co['name'],
        'tagline': old_co.get('reason', ''),
        'data': {},
        'confidence': 'unknown',
        'notes': '数据保留自上次验证'
    }
    for group in old_groups:
        for row in group.get('rows', []):
            dim = row['label']
            cell_content = row['cells'][idx] if idx < len(row['cells']) else '暂无公开数据'
            if isinstance(cell_content, dict) and 'summary' in cell_content:
                cd['data'][dim] = normalize_cell(dim, cell_content)
            else:
                sources = row.get('sources', [])
                source = sources[idx] if idx < len(sources) else {'name': '公开资料', 'url': '#'}
                cd['data'][dim] = {
                    'summary': '待核验',
                    'confidence': 'low',
                    'note': '旧格式保留数据，待重新核验',
                    'bullets': [{
                        'text': str(cell_content),
                        'sources': [normalize_source(source)]
                    }]
                }
    return cd


def build_table_json(companies_data, published_date=None):
    """把各公司的结构化数据转换为 table.json 格式"""
    if published_date is None:
        published_date = datetime.date.today().isoformat()

    # 公司列表
    companies = []
    for cd in companies_data:
        companies.append({
            'name': cd['company'],
            'reason': cd.get('tagline', ''),
            'emphasis': False
        })

    # 分组 + 行数据
    groups = []
    for group_name, dims in DIMENSIONS.items():
        rows = []
        for dim in dims:
            cells = []
            sources = []
            for cd in companies_data:
                dim_data = cd['data'].get(dim, {
                    'summary': '待核验',
                    'confidence': 'low',
                    'note': '缺少该维度数据',
                    'bullets': [{'text': '暂无可靠公开数据', 'sources': [{'name': '待核验', 'url': '#'}]}]
                })
                cell = normalize_cell(dim, dim_data)
                cells.append(cell)
                first_sources = cell['bullets'][0].get('sources', []) if cell.get('bullets') else []
                sources.append(first_sources[0] if first_sources else {'name': '待核验', 'url': '#'})
            rows.append({
                'label': dim,
                'cells': cells,
                'sources': sources
            })
        groups.append({'label': group_name, 'rows': rows})

    return {
        'schema_version': 2,
        'verification_method': 'triangulated_evidence_v1',
        'published': published_date,
        'companies': companies,
        'groups': groups
    }


def generate_verification_report(companies_data, changes_summary):
    """生成人类可读的验证报告"""
    report_lines = []
    report_lines.append(f"# 三角验证报告 - {datetime.date.today().isoformat()}")
    report_lines.append("")
    report_lines.append(f"**公司数量**: {len(companies_data)}")
    report_lines.append(f"**维度数量**: {len(ALL_DIMS)}")
    report_lines.append(f"**生成时间**: {datetime.datetime.now().isoformat()}")
    report_lines.append("")

    if changes_summary:
        report_lines.append("## 本次变更摘要")
        report_lines.append("")
        for line in changes_summary:
            report_lines.append(f"- {line}")
        report_lines.append("")

    report_lines.append("## 各公司详细验证结果")
    report_lines.append("")

    for cd in companies_data:
        report_lines.append(f"### {cd['company']}")
        report_lines.append("")
        report_lines.append(f"**一句话描述**: {cd.get('tagline', '')}")
        report_lines.append(f"**整体置信度**: {cd.get('confidence', 'unknown')}")
        if cd.get('notes'):
            report_lines.append(f"**验证备注**: {cd['notes']}")
        report_lines.append("")

        report_lines.append("| 维度 | 小标题 | 置信度 | 要点与来源 |")
        report_lines.append("|------|--------|--------|------------|")
        for dim in ALL_DIMS:
            dim_data = normalize_cell(dim, cd['data'].get(dim, {}))
            bullet_texts = []
            for b in dim_data.get('bullets', []):
                srcs = []
                for s in b.get('sources', []):
                    src = normalize_source(s)
                    srcs.append(f"[{src['name']}]({src['url']})" if src['url'] != '#' else src['name'])
                bullet_texts.append(f"{b.get('text','-')}（{' / '.join(srcs)}）")
            content = "<br>".join(bullet_texts)
            report_lines.append(f"| {dim} | {dim_data['summary']} | {dim_data['confidence']} | {content} |")
        report_lines.append("")

    report_lines.append("---")
    report_lines.append(f"*此报告由自动化脚本生成于 {datetime.datetime.now().isoformat()}*")

    return '\n'.join(report_lines)


def main():
    parser = argparse.ArgumentParser(description='自动化三角验证具身智能公司数据')
    parser.add_argument('--only-pending', action='store_true', help='只处理新增公司')
    parser.add_argument('--all', action='store_true', help='刷新所有公司（高成本）')
    parser.add_argument('--company', type=str, help='刷新特定公司')
    parser.add_argument('--dry-run', action='store_true', help='只生成报告，不修改文件')
    parser.add_argument('--verbose', action='store_true', help='详细输出')
    args = parser.parse_args()

    print("=" * 60)
    print("🔍 具身智能赛道 · 自动化三角验证")
    print(f"运行时间: {datetime.datetime.now().isoformat()}")
    print("=" * 60)

    # 检查 API Key
    has_api_key = bool(
        os.environ.get('ANTHROPIC_API_KEY')
        or os.environ.get('OPENAI_API_KEY')
        or os.environ.get('QWEN_API_KEY')
    )
    if not has_api_key:
        print("\n⚠️  未检测到 LLM API Key（ANTHROPIC_API_KEY、OPENAI_API_KEY 或 QWEN_API_KEY）")
        print("   请在 GitHub Settings → Secrets and variables → Actions 中添加 API Key。")
        print("   新增公司会先以低置信度占位进入矩阵，后续配置 API Key 后再补齐。")

    # 读取现有数据
    existing_table = load_json(TABLE_PATH, default={
        'published': datetime.date.today().isoformat(),
        'companies': [],
        'groups': []
    })
    existing_companies = {c['name']: c for c in existing_table.get('companies', [])}

    # 读取待处理公司
    pending_companies = []
    if PENDING_PATH.exists():
        pending = load_json(PENDING_PATH, [])
        if pending:
            pending_companies = [c.get('name', str(c)) for c in pending]
            print(f"\n待处理公司列表 ({len(pending_companies)}): {', '.join(pending_companies)}")

    # 确定要处理哪些公司
    companies_to_process = []
    if args.company:
        companies_to_process = [args.company]
    elif args.only_pending and pending_companies:
        companies_to_process = pending_companies
    elif args.all:
        companies_to_process = list(existing_companies.keys()) + pending_companies
    else:
        # 默认：每日全量三角核验已有公司 + 新增公司
        companies_to_process = list(existing_companies.keys()) + pending_companies
        print(f"\n默认模式：每日全量核验 {len(existing_companies)} 家现有公司 + 新增公司")

    print(f"\n本次共处理 {len(companies_to_process)} 家公司:")
    for c in companies_to_process:
        print(f"  - {c}{' (新)' if c in pending_companies else ''}")

    # 处理每家公司
    results = []
    failed = []

    for company_name in companies_to_process:
        try:
            existing_data = extract_existing_company_data(existing_table, company_name)
            is_new = company_name in pending_companies or existing_data is None
            if not has_api_key:
                if is_new:
                    result = build_placeholder_company(company_name, '未配置自动核验 API Key，先占位待补充')
                else:
                    print(f"\n  → 跳过已有公司: {company_name}（无 API Key，不覆盖现有数据）")
                    result = None
            else:
                result = process_company(company_name, existing_data, is_new)
                if result is None and is_new:
                    result = build_placeholder_company(company_name, '自动核验暂未完成，先占位待复核')
            if result:
                results.append(result)
            else:
                failed.append(company_name)
        except Exception as e:
            print(f"  ❌ 处理 {company_name} 时出错: {e}")
            failed.append(company_name)

    # 汇总变更
    changes_summary = []
    if results:
        changes_summary.append(f"成功处理 {len(results)} 家公司")
    if failed:
        changes_summary.append(f"失败/跳过 {len(failed)} 家: {', '.join(failed)}")

    # 生成新的 table.json（合并模式：保留原有未处理的公司数据）
    if results and not args.dry_run:
        # 合并：保留原有顺序，用新结果替换原列；纯新增公司追加到末尾
        processed_names = {cd['company'] for cd in results}
        processed_by_name = {cd['company']: cd for cd in results}

        all_companies_data = []
        old_groups = existing_table.get('groups', [])
        old_companies_list = existing_table.get('companies', [])

        for idx, old_co in enumerate(old_companies_list):
            name = old_co['name']
            if name in processed_by_name:
                all_companies_data.append(processed_by_name[name])
            else:
                all_companies_data.append(restore_company_from_table(old_co, idx, old_groups))

        for cd in results:
            if cd['company'] not in existing_companies:
                all_companies_data.append(cd)

        new_table = build_table_json(all_companies_data)
        save_json(TABLE_PATH, new_table)

        # 生成验证报告
        report = generate_verification_report(all_companies_data, changes_summary)
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\n✓ 验证报告已保存: {REPORT_PATH.name}")

        # 如果成功处理了待处理公司，清理 pending 列表
        if pending_companies:
            remaining = [c for c in pending if c.get('name', '') not in processed_names]
            if remaining != pending:
                save_json(PENDING_PATH, remaining)
                print(f"✓ 已更新待处理公司列表 (剩余 {len(remaining)} 家)")
    else:
        # 只生成报告
        if results:
            report = generate_verification_report(results, changes_summary + ['dry-run 模式，未修改文件'])
            with open(REPORT_PATH, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n✓ 验证报告已保存: {REPORT_PATH.name}")

    print(f"\n{'=' * 60}")
    print(f"完成: 成功 {len(results)}, 失败/跳过 {len(failed)}")
    if failed:
        print(f"失败列表: {', '.join(failed)}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
