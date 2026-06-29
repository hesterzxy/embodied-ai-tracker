# V2 Workspace

V2 is an isolated workspace for experimenting with persistent company add/remove flows.

- Public entry: `/v2/`
- V2 matrix data: `v2/data/table.json`
- Shared news data: `data/news.json`
- Stable V1 entry remains `/` and continues to read `data/table.json`

Implementation rule: V2 features that change the company list should write only to
`v2/data/table.json` unless explicitly promoted back to V1.

The browser UI supports temporary local add/hide controls for quick comparison.
When deployed on Vercel, the add-company control also posts to `/api/add-company`,
which dispatches the `V2 Company Management` GitHub Actions workflow. Persistent
add/remove operations update only `v2/data/table.json`.

On add, the workflow first gathers company-specific evidence, then asks the
configured LLM API to draft a structured matrix column. V2 only writes that
column if it passes validation: enough source-backed cells, no `待研判` filler,
bounded recent highlights, and multiple usable URLs. If validation fails, the
company remains a pending candidate instead of publishing low-quality analysis.

The add workflow also runs `scripts/v2_research_news.py` first. That script does
a company-specific fetch against the existing robotics news sources and stores
the evidence in `v2/data/research_news.json`; `scripts/v2_company.py` then reads
both the shared news feed and this V2-only research cache. This keeps V2
experiments separate from the stable V1 data.
