# OpsWatch web

A dependency-free dashboard for historical offline anomaly assessments. The backend serves this directory; it requires no frontend build, npm install, external fonts, CDN assets, or API keys. Browser-native ES modules are used.

The page fetches `GET /api/report` and `GET /api/events` from the same origin. Start the repository’s Python server, then open its root URL. Opening `index.html` directly will not provide the API. The **Refresh assessment** button reloads both endpoints. The dashboard never polls, generates sample values, or claims to monitor production systems.

## API contract

`/api/report` returns an object with `status: "ready" | "not_ready"`, optional `dataset: {name, source_url, details}`, `model: {name, score_semantics}`, `evaluation`, `split`, and `limitations: string[]`. Evaluation rate fields (`precision`, `recall`, `f1`, `average_precision`, `baseline_precision`, `baseline_recall`, `baseline_f1`) are numbers between zero and one. Evaluation also includes `threshold`, `test_windows`, and `anomalous_windows`. Split fields `train`, `validation`, and `test` contain `{windows, anomalous_windows, start, end}`. Null or absent measurements display **Not reported** or an em dash. A `not_ready` report shows an honest empty state.

`/api/events` returns `{events: [{timestamp, window_start, score, predicted_anomaly, actual_anomaly, messages}]}`. `timestamp` or fallback `window_start` is an ISO UTC window start. Prediction and actual label are boolean or null; unknown labels are never converted to normal. `messages` is an array of source excerpt strings. The backend defines score semantics; the frontend does not assume calibration. Unknown event shapes produce a visible error rather than silent coercion.

## Interactions

- Summary cards and model/baseline bars use only returned finite measurements. A percentage-point comparison is derived only when both values are reported.
- The event explorer searches source messages and timestamps, filters prediction/outcome/inclusive UTC dates, paginates 40 rows, and expands exact source excerpts. Prediction and known label remain separate.
- The score timeline uses up to the last 300 matching windows with a real timestamp and finite score. It never interpolates additional records. Exact values remain in the table.
- Filtered CSV includes timestamps, scores, predictions, labels, outcomes, and source messages. Formula-like fields are escaped.
- Evaluation notes show split sizes/date ranges, supplied limitations, and inspectable report JSON. No data is modified by this UI.

Navigation, form labels, visible focus, keyboard-accessible evidence toggles, reduced motion, readable mobile inputs, and contained table scrolling are included. Fetch errors appear separately for report and events, so one unavailable endpoint does not conceal the other.

## Verification

Node 24+ is needed only for tests:

```sh
cd web
npm test
```

Tests cover zero/missing metrics, schema validation, nullable labels, chronological order, all confusion outcomes, inclusive UTC filters, source preservation, URL safety, and CSV escaping. No packages are installed.
