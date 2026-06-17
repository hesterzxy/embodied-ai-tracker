import json

with open('data/table.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 1. Remove the first company from an older table export
data['companies'] = data['companies'][1:]

# 2. For each row, remove first cell and first source
for g in data['groups']:
    for r in g['rows']:
        r['cells'] = r['cells'][1:]
        if 'sources' in r and isinstance(r['sources'], list):
            r['sources'] = r['sources'][1:]
            # Convert strings to objects
            new_sources = []
            for s in r['sources']:
                if isinstance(s, str):
                    new_sources.append({'name': s, 'url': '#'})
                else:
                    new_sources.append(s)
            r['sources'] = new_sources

with open('data/table.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print('Reformatted table.json: removed first company, adjusted cells & sources.')
