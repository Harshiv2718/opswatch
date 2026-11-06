import test from 'node:test';
import assert from 'node:assert/strict';
import { count, eventsCsv, filterEvents, formatTimestamp, normalizeEvents, normalizeReport, outcomeFor, percentage, safeUrl } from './data.js';

test('zero metrics are real values, while missing, invalid and out-of-range rates stay unreported', () => {
  assert.equal(percentage(0), '0%');
  assert.equal(percentage(0.875), '87.5%');
  for (const value of [null, undefined, NaN, Infinity, -0.1, 1.1, '0.9']) assert.equal(percentage(value), '—');
  assert.equal(count(0), 0);
  assert.equal(count(1.2), null);
});
test('report format accepts honest not-ready state and nullable sections', () => {
  assert.equal(normalizeReport({ status: 'not_ready', evaluation: null }).status, 'not_ready');
  assert.throws(() => normalizeReport({ status: 'live' }), /expected/);
  assert.throws(() => normalizeReport({ status: 'ready', evaluation: [] }), /evaluation/);
});
test('events preserve evidence, unknown labels and exact zero scores, and sort by actual UTC timestamp', () => {
  const events = normalizeEvents({ events: [
    { timestamp: '2026-11-06T10:00:00Z', score: 0, predicted_anomaly: false, actual_anomaly: null, messages: ['Source line'] },
    { window_start: '2026-11-05T10:00:00Z', score: 0.8, predicted_anomaly: true, actual_anomaly: true, messages: [] },
    { score: null, messages: null },
  ] });
  assert.equal(events.length, 3);
  assert.equal(events[0].timestamp, '2026-11-05T10:00:00Z');
  assert.equal(events[1].score, 0);
  assert.equal(events[1].actual_anomaly, null);
  assert.deepEqual(events[1].messages, ['Source line']);
  assert.equal(events[2].timestamp, null);
  assert.equal(outcomeFor(events[2]), 'unknown');
});
test('invalid event booleans, source messages and numeric scores are reported instead of coerced', () => {
  assert.throws(() => normalizeEvents({ events: [{ predicted_anomaly: 'false' }] }), /prediction/);
  assert.throws(() => normalizeEvents({ events: [{ actual_anomaly: 1 }] }), /known label/);
  assert.throws(() => normalizeEvents({ events: [{ score: '0.5' }] }), /non-numeric/);
  assert.throws(() => normalizeEvents({ events: [{ messages: [42] }] }), /messages/);
  assert.throws(() => normalizeEvents([]), /events array/);
});
test('filters distinguish prediction from known truth and retain unlabelled records', () => {
  const events = normalizeEvents({ events: [
    { timestamp: '2026-11-05T23:30:00-02:00', score: 0.9, predicted_anomaly: true, actual_anomaly: false, messages: ['Timeout at gateway'] },
    { timestamp: '2026-11-06T23:59:00Z', score: 0.2, predicted_anomaly: false, actual_anomaly: true, messages: ['Retry exceeded'] },
    { timestamp: null, predicted_anomaly: null, actual_anomaly: null, messages: [] },
  ] });
  assert.equal(filterEvents(events, { prediction: 'anomaly' }).length, 1);
  assert.equal(filterEvents(events, { outcome: 'fp' })[0].score, 0.9);
  assert.equal(filterEvents(events, { outcome: 'fn' })[0].score, 0.2);
  assert.equal(filterEvents(events, { outcome: 'unknown' }).length, 1);
  assert.equal(filterEvents(events, { search: 'GATEWAY' }).length, 1);
  assert.equal(filterEvents(events, { from: '2026-11-06', to: '2026-11-06' }).length, 2);
  assert.equal(filterEvents(events, { to: '2026-11-05' }).length, 0);
});
test('all confusion outcomes are calculated only when both booleans are known', () => {
  assert.equal(outcomeFor({ predicted_anomaly: true, actual_anomaly: true }), 'tp');
  assert.equal(outcomeFor({ predicted_anomaly: true, actual_anomaly: false }), 'fp');
  assert.equal(outcomeFor({ predicted_anomaly: false, actual_anomaly: true }), 'fn');
  assert.equal(outcomeFor({ predicted_anomaly: false, actual_anomaly: false }), 'tn');
  assert.equal(outcomeFor({ predicted_anomaly: false, actual_anomaly: null }), 'unknown');
});
test('CSV preserves real values, source quotes and newlines while neutralizing formula-like fields', () => {
  const events = normalizeEvents({ events: [{ timestamp: '2026-11-06T00:00:00Z', score: 0, predicted_anomaly: false, actual_anomaly: null, messages: ['  =SUM(A1:A2)', 'Quoted "message"\nnext line'] }] });
  const csv = eventsCsv(events);
  assert.ok(csv.includes('"0","false",""'));
  assert.ok(csv.includes("'  =SUM(A1:A2)"));
  assert.ok(csv.includes('Quoted ""message""\nnext line'));
});
test('only real web links are rendered as dataset source links', () => {
  assert.equal(safeUrl('https://example.org/dataset'), 'https://example.org/dataset');
  assert.equal(safeUrl('javascript:alert(1)'), null);
  assert.equal(safeUrl('/relative'), null);
  assert.equal(formatTimestamp(null), 'Not reported');
  assert.ok(formatTimestamp('2026-11-06T00:00:00Z').includes('Nov 6, 2026'));
});
