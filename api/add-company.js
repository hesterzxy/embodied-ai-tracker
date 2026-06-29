const DEFAULT_OWNER = 'hesterzxy';
const DEFAULT_REPO = 'embodied-ai-tracker';
const DEFAULT_WORKFLOW = 'v2-company.yml';
const DEFAULT_REF = 'main';

function json(res, status, body) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.end(JSON.stringify(body));
}

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') {
    return json(res, 200, { ok: true });
  }
  if (req.method !== 'POST') {
    return json(res, 405, { ok: false, error: 'Only POST is supported' });
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return json(res, 500, { ok: false, error: 'Missing GITHUB_TOKEN on server' });
  }

  let body = req.body;
  if (typeof body === 'string') {
    try {
      body = JSON.parse(body);
    } catch (error) {
      return json(res, 400, { ok: false, error: 'Invalid JSON body' });
    }
  }

  const companyName = String(body?.company_name || '').trim();
  const action = body?.action === 'remove' ? 'remove' : 'add';
  if (!companyName) {
    return json(res, 400, { ok: false, error: 'Missing company_name' });
  }
  if (companyName.length > 80) {
    return json(res, 400, { ok: false, error: 'company_name is too long' });
  }

  const owner = process.env.GITHUB_OWNER || DEFAULT_OWNER;
  const repo = process.env.GITHUB_REPO || DEFAULT_REPO;
  const workflow = process.env.GITHUB_WORKFLOW || DEFAULT_WORKFLOW;
  const ref = process.env.GITHUB_REF_NAME || DEFAULT_REF;

  const url = `https://api.github.com/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`;
  const ghRes = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'Content-Type': 'application/json',
      'X-GitHub-Api-Version': '2022-11-28',
      'User-Agent': 'embodied-ai-tracker',
    },
    body: JSON.stringify({
      ref,
      inputs: {
        action,
        company_name: companyName,
      },
    }),
  });

  if (!ghRes.ok) {
    const text = await ghRes.text();
    return json(res, 502, {
      ok: false,
      error: 'GitHub workflow dispatch failed',
      detail: text.slice(0, 500),
    });
  }

  return json(res, 200, {
    ok: true,
    message: 'Submitted to V2 GitHub Actions',
    action,
    company_name: companyName,
  });
};
