"""Dependency-free local privacy/status interface."""

# Embedded HTML/CSS/JS is kept readable in its native line-oriented form.
# ruff: noqa: E501

PRIVACY_DASHBOARD_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Synapse privacy status</title>
  <style>
    :root { color-scheme: dark; --bg:#0b1020; --panel:#141b2d; --line:#34415d;
      --text:#f5f7ff; --muted:#b8c2d9; --accent:#82d9c5; --warn:#ffd58a; }
    *,*::before,*::after { box-sizing: border-box; }
    body { margin:0; background:var(--bg); color:var(--text); font:16px/1.5 system-ui,sans-serif; }
    main { width:min(70rem,100%); margin:auto; padding:clamp(1rem,4vw,3rem); }
    header { display:flex; flex-wrap:wrap; justify-content:space-between; gap:1rem; align-items:center; }
    h1,h2 { line-height:1.15; }
    h1 { margin:.2rem 0; font-size:clamp(2rem,7vw,4rem); }
    .eyebrow { color:var(--accent); font-weight:700; letter-spacing:.08em; text-transform:uppercase; }
    .mode { border:1px solid var(--accent); color:var(--accent); border-radius:999px; padding:.35rem .75rem; font-weight:700; }
    .lead { color:var(--muted); max-width:65ch; }
    .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(15rem,1fr)); gap:1rem; margin:2rem 0; }
    section,.card { background:var(--panel); border:1px solid var(--line); border-radius:1rem; padding:1.25rem; }
    .metric { font-size:2rem; font-weight:750; margin:.15rem 0; }
    dt { color:var(--muted); }
    dd { margin:0 0 .75rem; overflow-wrap:anywhere; }
    ul { padding-left:1.25rem; }
    .warning { color:var(--warn); }
    label { display:block; font-weight:700; margin-bottom:.35rem; }
    input { width:100%; color:var(--text); background:#090d18; border:1px solid var(--line); border-radius:.55rem; padding:.75rem; }
    button { margin-top:.75rem; border:0; border-radius:.55rem; padding:.75rem 1rem; background:var(--accent); color:#07110e; font-weight:800; cursor:pointer; }
    button:disabled { opacity:.6; cursor:wait; }
    :focus-visible { outline:3px solid #fff; outline-offset:3px; }
    code { color:var(--accent); }
    #operation-status { min-height:1.5rem; color:var(--muted); }
    @media (prefers-reduced-motion: reduce) { *,*::before,*::after { scroll-behavior:auto!important; animation:none!important; transition:none!important; } }
  </style>
</head>
<body>
<main>
  <header>
    <div><div class="eyebrow">User-controlled memory</div><h1>Synapse privacy status</h1></div>
    <span class="mode" id="mode">Checking…</span>
  </header>
  <p class="lead">Screenshots are encrypted before durable storage. Remote processing is off unless the server owner explicitly enables and configures it. This page reports actual local state, including incomplete deletion.</p>

  <div class="grid" aria-label="Memory status summary">
    <article class="card"><div class="eyebrow">Queued</div><p class="metric" id="queued">—</p><span class="lead">Stored and waiting</span></article>
    <article class="card"><div class="eyebrow">Failed</div><p class="metric" id="failed">—</p><span class="lead">Visible; retries are bounded</span></article>
    <article class="card"><div class="eyebrow">Deletion issues</div><p class="metric" id="delete-failed">—</p><span class="lead">Remain retryable</span></article>
    <article class="card"><div class="eyebrow">Retention</div><p class="metric"><span id="retention">—</span> days</p><span class="lead">Default class</span></article>
  </div>

  <div class="grid">
    <section aria-labelledby="providers-heading">
      <h2 id="providers-heading">Active providers</h2>
      <dl id="providers"><dt>Status</dt><dd>Loading local configuration…</dd></dl>
    </section>
    <section aria-labelledby="warnings-heading">
      <h2 id="warnings-heading">Privacy boundaries</h2>
      <ul id="warnings"><li>Loading…</li></ul>
    </section>
  </div>

  <section aria-labelledby="delete-heading">
    <h2 id="delete-heading">Delete a memory</h2>
    <p class="lead">Deletion tombstones search first, then reports completion independently for encrypted blob, local index, vector, and graph stores. A partial failure is never shown as complete.</p>
    <form id="delete-form">
      <label for="content-id">Memory source ID</label>
      <input id="content-id" name="content-id" required pattern="mem-[0-9a-f]{40}" autocomplete="off" aria-describedby="delete-help">
      <small id="delete-help" class="lead">Use the <code>mem-…</code> source ID returned by upload or search.</small><br>
      <button id="delete-button" type="submit">Delete from configured stores</button>
    </form>
    <p id="operation-status" role="status" aria-live="polite"></p>
  </section>
</main>
<script>
const text = (id,value) => { document.getElementById(id).textContent = String(value); };
function renderProviders(values) {
  const root = document.getElementById('providers');
  const fragment = document.createDocumentFragment();
  for (const [name,value] of Object.entries(values)) {
    const term = document.createElement('dt');
    term.textContent = name.replace('_',' ');
    const description = document.createElement('dd');
    description.textContent = String(value);
    fragment.append(term, description);
  }
  root.replaceChildren(fragment);
}
function renderWarnings(values) {
  const root = document.getElementById('warnings');
  const items = values.map(value => {
    const item = document.createElement('li');
    item.className = 'warning';
    item.textContent = String(value);
    return item;
  });
  root.replaceChildren(...items);
}
async function refresh() {
  try {
    const response = await fetch('/privacy/status', {headers:{'Accept':'application/json'}});
    if (!response.ok) throw new Error('status unavailable');
    const status = await response.json();
    text('mode', status.mode === 'local-only' ? 'Local-only' : 'Remote enabled');
    text('queued', status.queue_counts.stored || 0);
    text('failed', status.queue_counts.failed || 0);
    text('delete-failed', status.deletion_counts.failed || 0);
    text('retention', status.default_retention_days);
    renderProviders(status.providers);
    renderWarnings(status.warnings);
  } catch (_) {
    text('mode','Status unavailable');
    text('operation-status','The local service did not return privacy status.');
  }
}
document.getElementById('delete-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.getElementById('delete-button');
  const contentId = document.getElementById('content-id').value;
  button.disabled = true;
  text('operation-status','Deleting from configured stores…');
  try {
    const response = await fetch(`/memory/${encodeURIComponent(contentId)}`, {
      method:'DELETE', headers:{'X-Synapse-Intent':'delete','Accept':'application/json'}
    });
    const receipt = await response.json();
    if (!response.ok) throw new Error(receipt.message || 'Deletion request failed.');
    const failed = receipt.stores.filter(item => item.state === 'failed').map(item => item.store);
    text('operation-status', receipt.complete ? 'Deletion completed in every configured store.' : `Deletion remains incomplete: ${failed.join(', ') || 'pending stores'}.`);
    await refresh();
  } catch (error) { text('operation-status', error.message || 'Deletion request failed.'); }
  finally { button.disabled = false; }
});
refresh();
</script>
</body>
</html>"""
