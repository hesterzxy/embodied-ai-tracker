#!/usr/bin/env python3
"""Validate URLs used by the matrix and news feed.

Outputs data/link_validation_report.md and exits non-zero when --fail-on-invalid
is passed and invalid links are found.
"""
import argparse
import json
import socket
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
TABLE_PATH = ROOT / "data" / "table.json"
NEWS_PATH = ROOT / "data" / "news.json"
REPORT_PATH = ROOT / "data" / "link_validation_report.md"

UNSTABLE_DOMAINS = {"m.toutiao.com", "toutiao.com", "xueqiu.com"}
OK_STATUS = {200, 201, 202, 204, 301, 302, 303, 307, 308}
NOT_FOUND_MARKERS = ("页面没有找到", "page not found", "404 not found")


def iter_sources():
    table = json.loads(TABLE_PATH.read_text(encoding="utf-8"))
    for group in table.get("groups", []):
        for row in group.get("rows", []):
            for company, cell in zip(table.get("companies", []), row.get("cells", [])):
                if isinstance(cell, dict) and cell.get("kind") == "synthesis":
                    continue
                for bullet in cell.get("bullets", []):
                    for src in bullet.get("sources", []):
                        url = src.get("url", "#") if isinstance(src, dict) else str(src)
                        yield {
                            "area": "matrix",
                            "company": company.get("name", ""),
                            "dimension": row.get("label", ""),
                            "text": bullet.get("text", ""),
                            "name": src.get("name", "") if isinstance(src, dict) else str(src),
                            "url": url,
                        }

    news = json.loads(NEWS_PATH.read_text(encoding="utf-8"))
    for item in news.get("items", []):
        yield {
            "area": "news",
            "company": item.get("company", ""),
            "dimension": item.get("category", ""),
            "text": item.get("title", ""),
            "name": item.get("source_name", ""),
            "url": item.get("url", "#"),
        }


def check_url(url, timeout):
    if not url or url == "#":
        return "no_url", "no URL"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid_url", "not an HTTP URL"
    if parsed.netloc.lower() in UNSTABLE_DOMAINS:
        unstable = True
    else:
        unstable = False
    last_error = None
    for _ in range(2):
        try:
            req = Request(url, method="GET", headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
                status = getattr(resp, "status", 200)
                sample = resp.read(4096).decode("utf-8", "ignore").lower()
                if any(marker in sample for marker in NOT_FOUND_MARKERS):
                    return "invalid", "not found page"
                break
        except HTTPError as e:
            status = e.code
            break
        except (URLError, TimeoutError, socket.timeout) as e:
            last_error = e
        except Exception as e:
            last_error = e
    else:
        return "invalid", type(last_error).__name__

    if status in OK_STATUS:
        return ("unstable" if unstable else "ok"), f"HTTP {status}"
    if status == 403:
        return ("unstable" if unstable else "blocked"), "HTTP 403"
    return "invalid", f"HTTP {status}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--fail-on-invalid", action="store_true")
    args = parser.parse_args()

    rows = []
    invalid_count = 0
    checked_urls = {}
    for src in iter_sources():
        url = src["url"]
        if url in checked_urls:
            status, detail = checked_urls[url]
        else:
            status, detail = check_url(url, args.timeout)
            checked_urls[url] = (status, detail)
        if status in {"invalid", "invalid_url", "blocked"}:
            invalid_count += 1
        rows.append({**src, "status": status, "detail": detail})

    now = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    lines = [f"# Link Validation Report", "", f"Generated: {now}", ""]
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    lines.append("## Summary")
    lines.append("")
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")
    lines.append("")
    lines.append("## Details")
    lines.append("")
    lines.append("| Area | Company | Dimension | Status | Source | URL | Text |")
    lines.append("|------|---------|-----------|--------|--------|-----|------|")
    for r in rows:
        if r["status"] == "ok":
            continue
        safe_text = str(r["text"]).replace("|", " / ")[:80]
        safe_name = str(r["name"]).replace("|", " / ")
        lines.append(
            f"| {r['area']} | {r['company']} | {r['dimension']} | {r['status']} ({r['detail']}) | "
            f"{safe_name} | {r['url']} | {safe_text} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {REPORT_PATH}")
    print(f"invalid links: {invalid_count}")
    if args.fail_on_invalid and invalid_count:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
