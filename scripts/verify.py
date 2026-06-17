#!/usr/bin/env python3
import json, sys
sys.path.insert(0, '.')
from fetch_news import is_relevant, categorize

with open('data/news.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
items = data.get('items', [])
out = []
out.append(f'总数: {len(items)} 条')
out.append('')
from collections import Counter
cats = Counter(it.get('category') for it in items)
out.append('分类分布:')
for k, v in sorted(cats.items(), key=lambda x: -x[1]):
    out.append(f'  {k}: {v} 条')
out.append('')
out.append('前15条标题:')
for i, it in enumerate(items[:15]):
    out.append(f'  [{it.get("date","?")}] [{it.get("category","?")}] {it.get("title","")[:80]}')
out.append('')
out.append('被过滤掉的旧新闻 (is_relevant=False):')
filtered_count = 0
for it in data.get('items', []):
    t = it.get('title', '').lower()
    if not is_relevant(it.get('title', '')):
        filtered_count += 1
        if filtered_count <= 10:
            out.append(f'  X {it.get("title","")[:80]}')
out.append(f'  ... 共 {filtered_count} 条不相关新闻被过滤')
out.append('')
with open('verify_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))
print('OK - see verify_result.txt')
