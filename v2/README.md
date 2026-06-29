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
