export const isRecord = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
export const numeric = (value) => typeof value === 'number' && Number.isFinite(value) ? value : null;
export const probability = (value) => numeric(value) !== null && value >= 0 && value <= 1 ? value : null;
export const count = (value) => Number.isSafeInteger(value) && value >= 0 ? value : null;
export const percentage = (value) => probability(value) === null ? '—' : `${(value * 100).toLocaleString('en', { maximumFractionDigits: 1 })}%`;
export const decimal = (value) => numeric(value) === null ? '—' : value.toLocaleString('en', { maximumFractionDigits: 4 });
export const integer = (value) => count(value) === null ? '—' : value.toLocaleString('en');
export function safeUrl(value) { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? url.href : null; } catch { return null; } }
export function validTimestamp(value) { return typeof value === 'string' && value.trim() && Number.isFinite(Date.parse(value)) ? value : null; }
export function formatTimestamp(value, dateOnly = false) {
  if (!validTimestamp(value)) return 'Not reported';
  return new Intl.DateTimeFormat('en', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric', ...(dateOnly ? {} : { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }) }).format(new Date(value));
}
export function normalizeReport(value) {
  if (!isRecord(value) || !['ready', 'not_ready'].includes(value.status)) throw new Error('The report response does not match the expected historical evaluation format.');
  for (const key of ['dataset', 'model', 'evaluation', 'split']) if (value[key] != null && !isRecord(value[key])) throw new Error(`The report ${key} section could not be read.`);
  return value;
}
export function normalizeEvents(value) {
  if (!isRecord(value) || !Array.isArray(value.events)) throw new Error('The event response must contain a historical events array.');
  if (value.events.length > 200000) throw new Error('This event response is too large to explore in the browser. Use a smaller historical export.');
  return value.events.map((event, index) => {
    if (!isRecord(event)) throw new Error(`Historical window ${index + 1} is not a valid event.`);
    const messages = event.messages == null ? [] : Array.isArray(event.messages) && event.messages.every((message) => typeof message === 'string') ? event.messages : null;
    if (messages === null) throw new Error(`Historical window ${index + 1} has unreadable source messages.`);
    if (event.predicted_anomaly != null && typeof event.predicted_anomaly !== 'boolean') throw new Error(`Historical window ${index + 1} has an invalid prediction.`);
    if (event.actual_anomaly != null && typeof event.actual_anomaly !== 'boolean') throw new Error(`Historical window ${index + 1} has an invalid known label.`);
    if (event.score != null && numeric(event.score) === null) throw new Error(`Historical window ${index + 1} has a non-numeric score.`);
    return { ...event, _index: index, timestamp: validTimestamp(event.timestamp) || validTimestamp(event.window_start), score: numeric(event.score), predicted_anomaly: typeof event.predicted_anomaly === 'boolean' ? event.predicted_anomaly : null, actual_anomaly: typeof event.actual_anomaly === 'boolean' ? event.actual_anomaly : null, messages };
  }).sort((a, b) => (a.timestamp ? Date.parse(a.timestamp) : Infinity) - (b.timestamp ? Date.parse(b.timestamp) : Infinity) || a._index - b._index);
}
export function outcomeFor(event) {
  if (event.actual_anomaly === null || event.predicted_anomaly === null) return 'unknown';
  return event.predicted_anomaly ? event.actual_anomaly ? 'tp' : 'fp' : event.actual_anomaly ? 'fn' : 'tn';
}
export function filterEvents(events, { search = '', prediction = 'all', outcome = 'all', from = '', to = '' } = {}) {
  const term = search.trim().toLocaleLowerCase('en');
  return events.filter((event) => {
    if (term && ![event.timestamp || '', ...event.messages].some((text) => text.toLocaleLowerCase('en').includes(term))) return false;
    if (prediction !== 'all' && !(prediction === 'unknown' ? event.predicted_anomaly === null : event.predicted_anomaly === (prediction === 'anomaly'))) return false;
    if (outcome !== 'all' && outcomeFor(event) !== outcome) return false;
    if (from || to) {
      if (!event.timestamp) return false;
      const date = new Date(event.timestamp).toISOString().slice(0, 10);
      if (from && date < from || to && date > to) return false;
    }
    return true;
  });
}
export const outcomeNames = { tp: 'True positive', fp: 'False positive', fn: 'False negative', tn: 'True negative', unknown: 'Unlabeled / unknown' };
export function eventsCsv(events) {
  const escape = (value) => { let text = String(value ?? ''); if (/^[\s]*[=+@\-\t\r]/.test(text)) text = `'${text}`; return `"${text.replaceAll('"', '""')}"`; };
  return [['Timestamp UTC', 'Score', 'Predicted anomaly', 'Known anomaly label', 'Outcome', 'Source messages'], ...events.map((event) => [event.timestamp || '', event.score, event.predicted_anomaly, event.actual_anomaly, outcomeNames[outcomeFor(event)], event.messages.join('\n')])].map((row) => row.map(escape).join(',')).join('\r\n');
}
