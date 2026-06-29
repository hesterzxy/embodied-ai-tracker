# Vercel deployment notes

This project can run as a static site plus one Vercel Serverless Function:

- `index.html` serves the tracker UI.
- `api/add-company.js` receives a company name and triggers the V2 GitHub Actions workflow.

## Required Vercel environment variables

Set these in Vercel Project Settings -> Environment Variables:

- `GITHUB_TOKEN`: GitHub fine-grained token. Required.
- `GITHUB_OWNER`: optional, defaults to `hesterzxy`.
- `GITHUB_REPO`: optional, defaults to `embodied-ai-tracker`.
- `GITHUB_WORKFLOW`: optional, defaults to `v2-company.yml`.
- `GITHUB_REF_NAME`: optional, defaults to `main`.

## GitHub token permissions

Use a fine-grained personal access token scoped only to this repository.
It needs permission to trigger workflows:

- Actions: Read and write
- Contents: Read-only is enough for dispatching workflow runs

Do not put this token in frontend JavaScript.

## V2 add-company flow

1. User enters a company name in the webpage.
2. Frontend POSTs to `/api/add-company`.
3. Vercel function calls GitHub Actions `workflow_dispatch`.
4. `.github/workflows/v2-company.yml` receives `action` and `company_name`.
5. The workflow runs `python scripts/v2_company.py --add "$COMPANY"` or `--remove`.
6. `v2/data/table.json` is committed. V1 `data/table.json` is not touched.

If the API call fails, the page falls back to local browser storage so the
company name is not lost.
