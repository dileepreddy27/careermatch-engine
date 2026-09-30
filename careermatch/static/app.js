const byId = (id) => document.getElementById(id);
const node = (tag, text, cls) => { const el = document.createElement(tag); el.textContent = text; if (cls) el.className = cls; return el; };
let busy = false;
async function loadDemo() {
  try {
    const response = await fetch('/api/demo');
    if (!response.ok) throw new Error('Demo inputs could not be loaded.');
    const data = await response.json();
    byId('resume').value = data.resume;
    byId('jobs').value = JSON.stringify(data.jobs, null, 2);
    byId('job-count').textContent = `· ${data.jobs.length} roles`;
    byId('status').className = '';
    byId('status').textContent = 'Synthetic inputs ready. Run a comparison.';
    byId('summary').replaceChildren();
    byId('results').replaceChildren(node('p', 'Run a comparison to inspect evidence for these inputs.', 'empty panel'));
  } catch (err) { showError(err.message); }
}
function showError(message) { byId('status').className = 'error'; byId('status').textContent = message; }
function render(data) {
  byId('summary').textContent = `${data.matches.length} roles · ${data.chunks} source chunks · ${data.mode}. Scores are ranking heuristics, not hiring probabilities.`;
  byId('results').replaceChildren();
  for (const job of data.matches) {
    const card = node('article', '', 'job');
    const top = node('div', '', 'job-top');
    const title = node('div', '');
    title.append(node('h3', job.title), node('p', job.company, 'company'));
    const score = node('div', '', 'score'); score.append(node('strong', job.rank_score.toFixed(0)), node('small', 'RANK / 100'));
    top.append(title, score); card.append(top);
    const chips = node('div', '', 'chips');
    for (const req of job.requirements) chips.append(node('span', `${req.status === 'supported' ? '✓' : 'Gap ·'} ${req.skill}`, `chip ${req.status === 'gap' ? 'gap' : ''}`));
    card.append(chips, node('p', job.requirements.length ? `${Math.round(job.coverage * 100)}% of extracted skills have source evidence · vector similarity ${job.vector_similarity.toFixed(2)}` : 'No recognized requirements. This role needs manual review.', 'explanation'));
    const details = node('details', ''); details.append(node('summary', 'Inspect sources & suggested excerpts'));
    const evidence = node('div', '', 'evidence');
    evidence.append(node('p', 'Consider moving these verbatim excerpts earlier in your resume. Read them in context before using them.'));
    for (const excerpt of job.suggested_excerpts) evidence.append(node('blockquote', excerpt.quote), node('cite', `${excerpt.section} · characters ${excerpt.start}–${excerpt.end} · ${excerpt.chunk_id}`));
    if (!job.suggested_excerpts.length) evidence.append(node('p', 'No supported excerpts. Do not add unsupported experience.'));
    for (const req of job.requirements) {
      const item = node('div', `${req.skill} — ${req.status === 'supported' ? 'source text found' : 'missing evidence'}`, 'requirement');
      item.append(node('q', req.job_quote)); evidence.append(item);
    }
    const download = node('button', 'Download review notes', 'export'); download.type = 'button';
    download.addEventListener('click', () => {
      const notes = [`# Review: ${job.title}`, job.company, data.disclaimer, '\n## Verbatim source excerpts', ...job.suggested_excerpts.map(x => `- ${x.quote}\n  Source: ${x.section}, characters ${x.start}-${x.end}`), '\n## Missing evidence', ...job.gaps.map(x => `- ${x}`)].join('\n\n');
      const url = URL.createObjectURL(new Blob([notes], {type:'text/markdown'}));
      const a = document.createElement('a'); a.href = url; a.download = 'careermatch-review.md'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    evidence.append(download); details.append(evidence); card.append(details); byId('results').append(card);
  }
}
byId('load').addEventListener('click', loadDemo);
byId('run').addEventListener('click', async () => {
  if (busy) return;
  busy = true; byId('run').disabled = true; byId('load').disabled = true;
  byId('status').className = ''; byId('status').textContent = 'Comparing requirements with your source document…';
  try {
    const response = await fetch('/api/match', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({resume:byId('resume').value, jobs:JSON.parse(byId('jobs').value)})});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the resume and job JSON fields. The API requires valid, bounded inputs.');
    render(data); byId('status').textContent = 'Comparison complete. Review the evidence and gaps.';
  } catch (err) { byId('results').replaceChildren(); byId('summary').textContent = ''; showError(err.message); }
  finally { busy = false; byId('run').disabled = false; byId('load').disabled = false; }
});
loadDemo();
