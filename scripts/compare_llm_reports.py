#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare Qwen and AI Code With output on the same news set.

This script is intended for manual GitHub Actions runs only. It does not update
data/news.json or any production output.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import fetch_news


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "news.json"


@dataclass
class Provider:
    name: str
    api_key: str
    api_url: str
    model: str


def normalize_chat_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if url.endswith("/v1"):
        return url + "/chat/completions"
    if not url.endswith("/chat/completions"):
        return url + "/v1/chat/completions"
    return url


def get_providers():
    qwen_key = (
        os.getenv("QWEN_API_KEY")
        or os.getenv("DASHSCOPE_API_KEY")
        or os.getenv("QWEN_KEY")
        or os.getenv("ALIYUN_API_KEY")
        or ""
    )
    aicodewith_key = os.getenv("AICODEWITH_API_KEY") or ""
    return [
        Provider(
            name="Qwen",
            api_key=qwen_key,
            api_url=normalize_chat_url(
                os.getenv("QWEN_API_URL")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
            ),
            model=os.getenv("QWEN_MODEL") or "qwen-plus",
        ),
        Provider(
            name="AI Code With",
            api_key=aicodewith_key,
            api_url=normalize_chat_url(os.getenv("OPENAI_BASE_URL") or os.getenv("AICODEWITH_BASE_URL") or ""),
            model=os.getenv("AICODEWITH_MODEL") or os.getenv("OPENAI_MODEL") or "",
        ),
    ]


def chat(provider: Provider, messages, temperature=0.1, max_tokens=1000):
    if not provider.api_key:
        return None, "missing api key"
    if not provider.api_url:
        return None, "missing api url"
    if not provider.model:
        return None, "missing model"
    payload = {
        "model": provider.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        provider.api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "embodied-ai-tracker-compare/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=80) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip(), ""
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return None, f"HTTP {exc.code}: {body[:800]}"
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def weekly_prompt(items, evidence):
    evidence_text = []
    for theme in evidence[:5]:
        evidence_text.append(f"主题：{theme['label']}")
        for item in theme["items"][:3]:
            evidence_text.append(f"- {fetch_news.evidence_line(item)}")

    category_lines = []
    for cat in fetch_news.REPORT_CATEGORIES:
        cat_items = [it for it in items if it.get("category") == cat]
        if not cat_items:
            continue
        category_lines.append(f"{cat}：")
        for item in cat_items[:8]:
            category_lines.append(f"- {fetch_news.evidence_line(item)}")

    return (
        "请基于以下具身智能周度新闻证据，生成高质量中文周报摘要。\n"
        "要求：\n"
        "1. 输出严格 JSON，不要 Markdown。\n"
        "2. insights 写 1-3 条，每条必须是“观点 + 关键事实 + 判断含义”；证据少时只写 1-2 条，不要硬凑。\n"
        "3. label 是观点短句，text 是一段完整概括；text 里不要再使用冒号。\n"
        "4. 不要使用“这对行业重要，因为”“这说明”“这意味着”这类模板化句式；把因果判断自然写进同一句话。\n"
        "5. 不要堆标题，不要出现《》引用标题，不要空泛套话。\n"
        "6. 只使用证据里的事实；证据不足就降低结论强度。\n"
        "JSON 格式：{\"insights\":[{\"label\":\"\",\"text\":\"\"}]}\n\n"
        "优先证据：\n" + "\n".join(evidence_text) + "\n\n"
        "分类新闻：\n" + "\n".join(category_lines)
    )


def parse_json_report(content):
    if not content:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", content.strip())
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        text = match.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    insights = data.get("insights")
    if not isinstance(insights, list):
        return None
    cleaned = []
    for item in insights[:3]:
        label = str(item.get("label", "")).strip()
        body = str(item.get("text", "")).strip()
        if label and body:
            cleaned.append({"label": label, "text": body})
    return cleaned


def translate_prompt(title):
    return [
        {
            "role": "system",
            "content": (
                "Translate robotics and embodied-AI news titles into concise Simplified Chinese. "
                "Preserve company/product names. Return only the translated title."
            ),
        },
        {"role": "user", "content": title},
    ]


def english_title_samples(items, limit=5):
    picked = []
    seen = set()
    for item in items:
        title = fetch_news.normalize_original_title_format(item.get("title", ""))
        match = re.search(r"\(([^()]*[A-Za-z][^()]*)\)$", title)
        original = match.group(1).strip() if match else title
        if not fetch_news.is_english_title(original):
            continue
        key = original.lower()
        if key in seen:
            continue
        seen.add(key)
        picked.append(original)
        if len(picked) >= limit:
            break
    return picked


def write_summary(markdown: str):
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown)
    print(markdown)


def main():
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    items = data.get("items", [])
    start, end = fetch_news.current_week_range()
    week_items = [item for item in items if fetch_news.in_week(item, start, end)]
    if not week_items:
        raise SystemExit("No current-week news items to compare.")

    evidence = fetch_news.build_report_evidence(week_items)
    prompt = weekly_prompt(week_items, evidence)
    title_samples = english_title_samples(items)

    lines = [
        "# LLM Weekly Report Comparison",
        "",
        f"- Week: {fetch_news.fmt_mmdd(start)} to {fetch_news.fmt_mmdd(end)}",
        f"- Current-week news items: {len(week_items)}",
        "",
    ]

    for provider in get_providers():
        lines.extend([f"## {provider.name}", "", f"- Model: `{provider.model or '(missing)'}`", ""])
        content, error = chat(
            provider,
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
        if error:
            lines.extend([f"Weekly report failed: `{error}`", ""])
        else:
            insights = parse_json_report(content)
            if not insights:
                lines.extend(["Weekly report returned non-JSON or empty output:", "", "```", content[:1500], "```", ""])
            else:
                for idx, item in enumerate(insights, 1):
                    lines.append(f"{idx}. **{item['label']}**：{item['text']}")
                lines.append("")

        if title_samples:
            lines.extend(["### Title Translation Samples", ""])
            for title in title_samples:
                translated, trans_error = chat(provider, translate_prompt(title), temperature=0.1, max_tokens=120)
                if trans_error:
                    lines.append(f"- `{title}` -> translation failed: `{trans_error}`")
                else:
                    lines.append(f"- `{title}` -> {translated}")
            lines.append("")

    write_summary("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
