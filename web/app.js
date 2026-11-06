import { count, decimal, eventsCsv, filterEvents, formatTimestamp, integer, isRecord, normalizeEvents, normalizeReport, numeric, outcomeFor, outcomeNames, percentage, probability, safeUrl } from './data.js';

const $ = (id) => document.getElementById(id);
const node = (tag, className = '', text) => { const element = document.createElement(tag); element.className = className; if (text !== undefined) element.textContent = text; return element; };
const show = (id, visible) => { $(id).hidden = !visible; };
const state = { report: null, eventPayload: null, events: [], filtered: [], page: 0, expanded: new Set(), loading: false };
const PAGE_SIZE = 40;
let noticeTimer;

function notify(message) { $('notification').textContent = message; show('notification', true); clearTimeout(noticeTimer); noticeTimer = setTimeout(() => show('notification', false), 6000); }
function setError(id, message) { $(id).replaceChildren(node('strong', '', 'This part of the assessment could not be loaded.'), node('p', '', message)); show(id, true); }
async function fetchJson(path) {
  let response;
  try { response = await fetch(path, { headers: { Accept: 'application/json' }, cache: 'no-store' }); }
  catch { throw new Error(`Could not reach ${path}. Check the server connection and refresh to retry.`); }
  if (!response.ok) throw new Error(`${path} returned HTTP ${response.status}. Check the evaluation artifacts and server, then refresh to retry.`);
  try { return await response.json(); } catch { throw new Error(`${path} did not return readable JSON.`); }
}
async function load() {
  if (state.loading) return;
  state.loading = true;
  $('refresh').disabled = true;
  $('refresh').setAttribute('aria-busy', 'true');
  show('loading', true); show('report-error', false); show('events-error', false);
  const [report, events] = await Promise.allSettled([fetchJson('/api/report').then(normalizeReport), fetchJson('/api/events').then((payload) => ({ payload, events: normalizeEvents(payload) }))]);
  if (report.status === 'fulfilled') { state.report = report.value; renderReport(); }
  else { state.report = null; show('report-content', false); show('report-empty', false); setError('report-error', report.reason.message); $('raw-report').textContent = 'The report could not be loaded.'; }
  if (events.status === 'fulfilled') { state.eventPayload = events.value.payload; state.events = events.value.events; state.page = 0; state.expanded.clear(); renderEvents(); }
  else { state.eventPayload = null; state.events = []; state.filtered = []; show('event-tools', false); show('events-empty', false); show('event-scope', false); $('export-events').disabled = true; $('event-count').textContent = 'Unavailable'; show('nav-event-count', false); setError('events-error', events.reason.message); }
  if (report.status === 'fulfilled' || events.status === 'fulfilled') $('load-time').textContent = `Loaded ${new Intl.DateTimeFormat('en', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'UTC' }).format(new Date())} UTC · not a live feed`;
  else $('load-time').textContent = 'Assessment unavailable · refresh to retry';
  show('loading', false);
  $('refresh').disabled = false;
  $('refresh').removeAttribute('aria-busy');
  state.loading = false;
}

function renderReport() {
  const report = state.report;
  const ready = report.status === 'ready';
  show('report-empty', !ready); show('report-content', ready);
  $('raw-report').textContent = JSON.stringify(report, null, 2);
  renderMethod(report);
  if (!ready) return;
  const dataset = report.dataset || {};
  const model = report.model || {};
  const evaluation = report.evaluation || {};
  $('dataset-name').textContent = typeof dataset.name === 'string' && dataset.name ? dataset.name : 'Not reported';
  $('model-name').textContent = typeof model.name === 'string' && model.name ? model.name : 'Not reported';
  const testSplit = report.split?.test;
  $('test-period').textContent = testSplit?.start && testSplit?.end ? `${formatTimestamp(testSplit.start, true)} – ${formatTimestamp(testSplit.end, true)}` : 'Not reported';
  const source = safeUrl(dataset.source_url);
  if (source) $('source-link').href = source;
  else $('source-link').removeAttribute('href');
  show('source-link', !!source);
  const metrics = [
    { key: 'f1', label: 'F1 score', description: 'The balance of precision and recall.', primary: true },
    { key: 'precision', label: 'Precision', description: 'How often predicted anomalies were labeled anomalous.' },
    { key: 'recall', label: 'Recall', description: 'How many labeled anomalies the model found.' },
    { key: 'average_precision', label: 'Average precision', description: 'A summary of ranking quality across thresholds.' },
  ];
  $('metrics').replaceChildren(...metrics.map((metric) => {
    const card = node('article', `metric-card ${metric.primary ? 'primary-metric' : ''}`);
    const value = probability(evaluation[metric.key]);
    card.append(node('span', 'metric-label', metric.label), node('strong', 'metric-value', percentage(value)), node('p', 'metric-description', value === null ? 'Not reported by the evaluation.' : metric.description));
    const baseline = probability(evaluation[`baseline_${metric.key}`]);
    if (value !== null && baseline !== null) {
      const difference = (value - baseline) * 100;
      card.append(node('p', 'metric-comparison', `${difference > 0 ? '+' : ''}${difference.toLocaleString('en', { maximumFractionDigits: 1 })} percentage points vs baseline`));
    } else if (metric.primary) card.append(node('p', 'metric-comparison', 'Baseline comparison not reported'));
    return card;
  }));
  $('comparison').replaceChildren(...['precision', 'recall', 'f1'].map((key) => {
    const row = node('div', 'comparison-row');
    row.append(node('span', 'comparison-label', { precision: 'Precision', recall: 'Recall', f1: 'F1 score' }[key]));
    const bars = node('div', 'comparison-bars');
    for (const [name, value] of [['Model', evaluation[key]], ['Baseline', evaluation[`baseline_${key}`]]]) {
      const group = node('div', `comparison-bar ${name.toLowerCase()}`);
      const track = node('div', 'bar-track');
      const fill = node('span', 'bar-fill');
      fill.style.width = `${probability(value) === null ? 0 : value * 100}%`;
      track.append(fill);
      const label = node('span', 'bar-value', probability(value) === null ? 'Not reported' : percentage(value));
      group.setAttribute('aria-label', `${name} ${key}: ${label.textContent}`);
      group.append(track, label); bars.append(group);
    }
    row.append(bars); return row;
  }));
  if (typeof evaluation.baseline_name === 'string' && evaluation.baseline_name) $('comparison').append(node('p', 'baseline-name', `Baseline: ${evaluation.baseline_name}`));
  const tradeoff = node('div', 'tradeoff-context');
  tradeoff.append(node('h3', '', 'The other side of the tradeoff.'));
  const table = node('table', 'tradeoff-table');
  const caption = node('caption', 'sr-only', 'Model and baseline tradeoffs from the complete held-out evaluation.');
  const head = node('thead'); const headings = node('tr');
  for (const label of ['Held-out metric', 'Model', 'Baseline']) { const th = node('th', '', label); th.scope = 'col'; headings.append(th); }
  head.append(headings);
  const body = node('tbody');
  for (const [label, modelValue, baselineValue] of [
    ['Recall', percentage(evaluation.recall), percentage(evaluation.baseline_recall)],
    ['Missed anomalous windows (FN)', integer(evaluation.confusion_matrix?.fn), integer(evaluation.baseline?.confusion_matrix?.fn)],
    ['False positive windows', integer(evaluation.confusion_matrix?.fp), integer(evaluation.baseline?.confusion_matrix?.fp)],
  ]) { const row = node('tr'); const labelCell = node('th', '', label); labelCell.scope = 'row'; row.append(labelCell, node('td', '', modelValue), node('td', '', baselineValue)); body.append(row); }
  table.append(caption, head, body); tradeoff.append(table, node('p', 'panel-footnote', 'Fewer false positives can come with more missed anomalies. Compare both against the same historical labels.'));
  $('comparison').append(tradeoff);
  const contextRows = [['Test windows', integer(evaluation.test_windows)], ['Labeled anomalous windows', integer(evaluation.anomalous_windows)], ['Decision threshold', decimal(evaluation.threshold)]];
  $('evaluation-context').replaceChildren(...contextRows.map(([label, value]) => { const row = node('div'); row.append(node('dt', '', label), node('dd', '', value)); return row; }));
  $('score-semantics').textContent = typeof model.score_semantics === 'string' && model.score_semantics ? model.score_semantics : 'Score semantics have not been reported. A score should not be interpreted as a calibrated probability without that context.';
}

function renderMethod(report) {
  const split = isRecord(report.split) ? report.split : {};
  const names = ['train', 'validation', 'test'];
  $('split-details').replaceChildren(...names.map((name) => {
    const data = isRecord(split[name]) ? split[name] : {};
    const card = node('div', `split-card split-${name}`);
    card.append(node('span', 'split-label', { train: 'Training', validation: 'Validation', test: 'Test' }[name]));
    const amount = node('strong', '', integer(data.windows)); amount.append(node('span', '', ' windows'));
    card.append(amount, node('p', '', count(data.anomalous_windows) === null ? 'Anomaly count not reported' : `${integer(data.anomalous_windows)} labeled anomalous`));
    card.append(node('small', '', data.start && data.end ? `${formatTimestamp(data.start, true)} – ${formatTimestamp(data.end, true)}` : 'Date range not reported'));
    return card;
  }));
  const items = ['This dashboard displays historical offline results. It does not monitor live systems or send alerts.'];
  if (Array.isArray(report.limitations)) for (const item of report.limitations) if (typeof item === 'string' && item.trim() && !items.includes(item.trim())) items.push(item.trim());
  if (items.length === 1) items.push('Additional dataset and model limitations have not been reported. Evaluate suitability before using these outputs in another setting.');
  $('limitations').replaceChildren(...items.map((item) => node('li', '', item)));
}

function getFilters() { return { search: $('search').value, prediction: $('prediction').value, outcome: $('outcome').value, from: $('from-date').value, to: $('to-date').value }; }
function renderEvents() {
  $('event-count').textContent = integer(state.events.length);
  $('nav-event-count').textContent = integer(state.events.length);
  show('nav-event-count', state.events.length > 0);
  show('events-empty', state.events.length === 0); show('event-tools', state.events.length > 0);
  const total = count(state.eventPayload?.total_windows) ?? count(state.report?.evaluation?.test_windows);
  const exported = count(state.eventPayload?.exported_windows) ?? state.events.length;
  const scope = typeof state.eventPayload?.scope === 'string' ? state.eventPayload.scope : '';
  $('event-scope').textContent = total !== null ? `${integer(exported)} supplied held-out windows of ${integer(total)} total. Summary metrics use all ${integer(total)} held-out windows.${scope ? ` Event scope: ${scope}.` : ''}` : `${integer(exported)} supplied historical windows.${scope ? ` Event scope: ${scope}.` : ' The complete evaluation window count has not been reported.'}`;
  show('event-scope', state.events.length > 0);
  $('export-events').disabled = state.events.length === 0;
  if (!state.events.length) return;
  const filters = getFilters();
  const invalidRange = filters.from && filters.to && filters.from > filters.to;
  show('filter-error', !!invalidRange);
  $('filter-error').textContent = invalidRange ? 'The end date must be on or after the start date.' : '';
  state.filtered = invalidRange ? [] : filterEvents(state.events, filters);
  $('export-events').disabled = state.filtered.length === 0;
  const pages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  state.page = Math.min(state.page, pages - 1);
  show('filter-empty', state.filtered.length === 0 && !invalidRange);
  show('table-container', state.filtered.length > 0); show('pagination', state.filtered.length > 0);
  renderScoreChart();
  const start = state.page * PAGE_SIZE;
  $('event-rows').replaceChildren(...state.filtered.slice(start, start + PAGE_SIZE).flatMap(renderEventRow));
  $('page-summary').textContent = `${(start + 1).toLocaleString('en')}–${Math.min(start + PAGE_SIZE, state.filtered.length).toLocaleString('en')} of ${state.filtered.length.toLocaleString('en')} matching windows · ${state.events.length.toLocaleString('en')} supplied`;
  $('page-number').textContent = `${state.page + 1} / ${pages}`;
  $('previous-page').disabled = state.page === 0;
  $('next-page').disabled = state.page === pages - 1;
}

function renderEventRow(event) {
  const row = node('tr', 'event-row');
  const date = node('td', 'window-cell');
  const button = node('button', 'window-button');
  const expanded = state.expanded.has(event._index);
  button.type = 'button'; button.setAttribute('aria-expanded', String(expanded)); button.setAttribute('aria-controls', `evidence-${event._index}`);
  button.append(node('span', 'expand-chevron', expanded ? '−' : '+'), node('span', '', formatTimestamp(event.timestamp)));
  button.addEventListener('click', () => { if (expanded) state.expanded.delete(event._index); else state.expanded.add(event._index); renderEvents(); const focus = document.querySelector(`[aria-controls="evidence-${event._index}"]`); focus?.focus({ preventScroll: true }); });
  date.append(button);
  const prediction = node('td'); prediction.append(node('span', `status-badge ${event.predicted_anomaly === true ? 'anomaly' : event.predicted_anomaly === false ? 'normal' : 'unknown'}`, event.predicted_anomaly === true ? 'Anomaly' : event.predicted_anomaly === false ? 'Normal' : 'Not reported'));
  const actual = node('td'); actual.append(node('span', `known-label ${event.actual_anomaly === true ? 'actual-anomaly' : ''}`, event.actual_anomaly === true ? 'Anomalous' : event.actual_anomaly === false ? 'Normal' : 'Unlabeled'));
  const outcome = outcomeFor(event);
  row.append(date, node('td', 'numeric-cell', decimal(event.score)), prediction, actual, node('td', `outcome outcome-${outcome}`, outcomeNames[outcome]), node('td', 'message-count', `${event.messages.length} excerpt${event.messages.length === 1 ? '' : 's'}`));
  const details = node('tr', 'evidence-row'); details.hidden = !expanded; details.id = `evidence-${event._index}`;
  const cell = node('td'); cell.colSpan = 6;
  const content = node('div', 'evidence-content'); content.append(node('h3', '', 'Source message excerpts'), node('p', 'evidence-help', 'Recorded messages returned with this window. Excerpts may be truncated by the evaluation pipeline.'));
  if (event.messages.length) { const messages = node('ol', 'message-list'); for (const message of event.messages) messages.append(node('li', '', message)); content.append(messages); }
  else content.append(node('p', 'not-reported', 'No source message excerpts were returned for this window.'));
  cell.append(content); details.append(cell);
  return [row, details];
}

function renderScoreChart() {
  const points = state.filtered.filter((event) => event.timestamp && numeric(event.score) !== null).slice(-300);
  show('score-chart', points.length >= 2);
  if (points.length < 2) return;
  const width = 1000; const height = 150; const left = 46; const right = 12; const top = 15; const bottom = 28;
  const times = points.map((event) => Date.parse(event.timestamp));
  const scores = points.map((event) => event.score);
  let min = Math.min(...scores); let max = Math.max(...scores);
  if (min === max) { const offset = Math.max(Math.abs(min) * 0.1, 0.05); min -= offset; max += offset; }
  const x = (index) => left + ((times[index] - times[0]) / (times.at(-1) - times[0] || 1)) * (width - left - right);
  const y = (score) => top + (1 - (score - min) / (max - min)) * (height - top - bottom);
  const svgNode = (tag, attributes = {}) => { const element = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value)); return element; };
  const svg = svgNode('svg', { viewBox: `0 0 ${width} ${height}`, preserveAspectRatio: 'none', role: 'img', 'aria-labelledby': 'score-chart-title score-chart-desc' });
  const title = svgNode('title', { id: 'score-chart-title' }); title.textContent = 'Historical scores for matching windows';
  const desc = svgNode('desc', { id: 'score-chart-desc' }); desc.textContent = `Last ${points.length} matching windows with a timestamp and score, in chronological order. An outlined point marks a predicted anomaly. Exact values are available in the table.`;
  svg.append(title, desc);
  for (const value of [min, (min + max) / 2, max]) {
    svg.append(svgNode('line', { x1: left, x2: width - right, y1: y(value), y2: y(value), class: 'score-grid' }));
    const label = svgNode('text', { x: left - 9, y: y(value) + 4, 'text-anchor': 'end', class: 'score-axis' }); label.textContent = decimal(value); svg.append(label);
  }
  svg.append(svgNode('polyline', { points: points.map((event, index) => `${x(index)},${y(event.score)}`).join(' '), class: 'score-line' }));
  points.forEach((event, index) => { if (event.predicted_anomaly) { const point = svgNode('circle', { cx: x(index), cy: y(event.score), r: 3.5, class: 'anomaly-point' }); const tooltip = svgNode('title'); tooltip.textContent = `${formatTimestamp(event.timestamp)} · score ${decimal(event.score)} · predicted anomaly`; point.append(tooltip); svg.append(point); } });
  const heading = node('div', 'score-chart-heading'); heading.append(node('strong', '', 'A score, with its timeline.'), node('span', '', `Last ${points.length} matching timed windows · not a live feed`), node('span', 'score-range', `Reported score range: ${decimal(Math.min(...scores))}–${decimal(Math.max(...scores))}`));
  const dates = node('div', 'score-dates'); dates.append(node('span', '', formatTimestamp(points[0].timestamp)), node('span', '', formatTimestamp(points.at(-1).timestamp)));
  $('score-chart').replaceChildren(heading, svg, dates);
}

$('refresh').addEventListener('click', load);
$('filters').addEventListener('submit', (event) => event.preventDefault());
$('filters').addEventListener('input', () => { state.page = 0; renderEvents(); });
$('clear-filters').addEventListener('click', () => { $('filters').reset(); state.page = 0; renderEvents(); $('search').focus(); });
$('previous-page').addEventListener('click', () => { state.page = Math.max(0, state.page - 1); renderEvents(); });
$('next-page').addEventListener('click', () => { state.page += 1; renderEvents(); });
$('export-events').addEventListener('click', () => { if (!state.filtered.length) return; const url = URL.createObjectURL(new Blob([eventsCsv(state.filtered)], { type: 'text/csv;charset=utf-8' })); const link = document.createElement('a'); link.href = url; link.download = 'opswatch-filtered-historical-events.csv'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); notify(`Exported ${state.filtered.length.toLocaleString('en')} matching historical windows.`); });
for (const link of document.querySelectorAll('.nav-link')) link.addEventListener('click', () => { for (const item of document.querySelectorAll('.nav-link')) { item.classList.toggle('active', item === link); if (item === link) item.setAttribute('aria-current', 'location'); else item.removeAttribute('aria-current'); } });
void load();
