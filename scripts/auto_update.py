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

# 14 个维度定义
DIMENSIONS = {
    '技术与团队': ['技术路线', '硬件能力', '大脑自研', '数据策略', '实测能力', '融资估值', '创始团队'],
    '产品化': ['量产进度', '可靠性'],
    '商业化': ['落地场景', '真实订单', '标杆客户', '价格', '商业模式']
}
ALL_DIMS = [d for group in DIMENSIONS.values() for d in group]

SYS_PROMPT = """你是一个严谨的产业研究分析师，专长是具身智能/人形机器人领域。
你的任务是搜集并验证公司信息，确保每个数据点都有公开来源支持。

关键原则:
1. **优先引用公开媒体报道** (36氪, 机器之心, 新华网, 科创板日报, 路透, Bloomberg 等)
2. **公司官网/官方公众号/官方发布会** 为一级证据
3. **融资估值数据必须有来源** (清科, 投中, 或媒体报道)
4. **出货量/量产数据最敏感**，必须有至少 2 个独立来源交叉验证
5. 如果没有可靠来源，明确标注「暂无公开数据」而不是猜测
6. 中文回答

输出格式是严格的 JSON (不要用 markdown 代码块):
{
  "company": "公司名称",
  "tagline": "一句话描述（如：整机量产最快 · 第1万台2026年3月下线）",
  "data": {
    "维度名称": {
      "content": "该维度的具体内容（可以用逗号或分号分隔不同要点）",
      "source_name": "来源名称和日期，如：36氪 2026-04",
      "source_url": "完整的来源 URL，或官网链接，或 '#' 表示无链接"
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

对于每个维度，请:
1. 明确写出该维度的核心信息（要点式，可多个要点）
2. 标注信息来源（媒体名称 + 大致日期）
3. 如果是融资、出货量、量产进度等关键数字，请确保来源可靠
4. 如果某维度无公开信息，content 字段填 "暂无公开数据"

{current_info}

请直接输出严格的 JSON 格式。"""


def process_company(company_name, existing_company=None, is_new=False):
    """处理单家公司：调用 LLM → 解析 → 返回结构化数据"""
    print(f"\n  → 正在验证: {company_name}")

    existing_data = None
    if existing_company and 'cells_by_dim' in existing_company:
        existing_data = existing_company['cells_by_dim']

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

    # 确保所有维度都有数据
    for dim in ALL_DIMS:
        if dim not in parsed['data']:
            parsed['data'][dim] = {
                'content': '暂无公开数据',
                'source_name': '公开资料',
                'source_url': '#'
            }

    print(f"    ✓ 已获取 {len(parsed['data'])} 个维度数据")
    print(f"    置信度: {parsed.get('confidence', 'unknown')}")
    if parsed.get('notes'):
        print(f"    备注: {parsed['notes'][:100]}")

    return parsed


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
                    'content': '暂无公开数据',
                    'source_name': '公开资料',
                    'source_url': '#'
                })
                cells.append(dim_data.get('content', '暂无公开数据'))
                sources.append({
                    'name': dim_data.get('source_name', '公开资料'),
                    'url': dim_data.get('source_url', '#')
                })
            rows.append({
                'label': dim,
                'cells': cells,
                'sources': sources
            })
        groups.append({'label': group_name, 'rows': rows})

    return {
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

        report_lines.append("| 维度 | 内容 | 来源 |")
        report_lines.append("|------|------|------|")
        for dim in ALL_DIMS:
            dim_data = cd['data'].get(dim, {})
            content = dim_data.get('content', '-').replace('\n', ' ')
            source_name = dim_data.get('source_name', '-')
            source_url = dim_data.get('source_url', '#')
            if source_url != '#':
                source = f"[{source_name}]({source_url})"
            else:
                source = source_name
            report_lines.append(f"| {dim} | {content[:100]} | {source} |")
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
    if not os.environ.get('ANTHROPIC_API_KEY') and not os.environ.get('OPENAI_API_KEY'):
        print("\n⚠️  未检测到 LLM API Key（ANTHROPIC_API_KEY 或 OPENAI_API_KEY）")
        print("   请先配置环境变量后再运行。")
        print("   export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

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
        # 默认：处理新增公司 + 刷新部分现有公司
        companies_to_process = pending_companies + list(existing_companies.keys())[:2]
        print(f"\n默认模式：处理新公司 + 刷新前 {min(2, len(existing_companies))} 家现有公司")

    print(f"\n本次共处理 {len(companies_to_process)} 家公司:")
    for c in companies_to_process:
        print(f"  - {c}{' (新)' if c in pending_companies else ''}")

    # 处理每家公司
    results = []
    failed = []

    for company_name in companies_to_process:
        try:
            is_new = company_name in pending_companies
            result = process_company(company_name, existing_companies.get(company_name), is_new)
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
        # 合并：保留原有公司，用新结果替换/添加
        all_companies_data = []
        processed_names = {cd['company'] for cd in results}

        # 先加已处理的新结果
        all_companies_data.extend(results)

        # 再保留原有的、未被处理的公司
        # 需要从原有 table.json 中恢复这些公司的数据结构
        # 注意：原有 table.json 的格式是行列结构，需要转换为按公司组织
        old_groups = existing_table.get('groups', [])
        old_companies_list = existing_table.get('companies', [])

        for idx, old_co in enumerate(old_companies_list):
            if old_co['name'] in processed_names:
                continue  # 已有新数据，跳过
            # 从原有行列结构中提取这家公司的数据
            cd = {
                'company': old_co['name'],
                'tagline': old_co.get('reason', ''),
                'data': {},
                'confidence': 'unknown',
                'notes': '数据保留自上次验证'
            }
            for group in old_groups:
                for row in group['rows']:
                    dim = row['label']
                    cell_content = row['cells'][idx] if idx < len(row['cells']) else '暂无公开数据'
                    source = row['sources'][idx] if idx < len(row['sources']) else {'name': '公开资料', 'url': '#'}
                    if isinstance(source, dict):
                        cd['data'][dim] = {
                            'content': cell_content,
                            'source_name': source.get('name', '公开资料'),
                            'source_url': source.get('url', '#')
                        }
                    else:
                        cd['data'][dim] = {
                            'content': cell_content,
                            'source_name': '公开资料',
                            'source_url': '#' if isinstance(source, str) and source.startswith('http') else source
                        }
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
