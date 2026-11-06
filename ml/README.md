# Historical BGL alert classification

This is a real, reproducible supervised ML pipeline. Its committed evaluation comes from the **complete official BGL archive**, not a synthetic generator or the 2,000-line parser example. It classifies already observed log windows against BGL alert-category tags. It does not predict future outages, verify incident impact, or run a live monitoring service.

## Reproduce the evaluation

Run from the repository root with Python 3.12:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r ml/requirements.txt
.venv/bin/python scripts/download_bgl.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python -m ml.pipeline train \
  --input data/raw/BGL.zip \
  --output artifacts \
  --scope "Complete official BGL.zip archive: all records streamed, including metadata-only records with empty messages; fixed 60-second occupied windows. No 2k sample used."
.venv/bin/python -m unittest discover -s tests -v
```

The download script verifies the publisher's MD5 before replacing the destination. The first full download in this environment took about 72 seconds; aggregation, training and evaluation took about 19 seconds. These are observations from one local run, not performance guarantees or benchmark comparisons. The ZIP is streamed directly without extracting archive paths.

Outputs:

| File | Contents |
| --- | --- |
| `artifacts/report.json` | Provenance, split boundaries, features, validation/test metrics, baselines, threshold and limitations |
| `artifacts/events.json` | Up to 500 evenly spaced, chronological held-out-window examples for the dashboard |
| `artifacts/model.joblib` | Fitted training scaler/classifier, chosen threshold, window size and feature schema |

The raw archive stays out of Git. Its dataset terms and citations are in [`data/NOTICE.md`](../data/NOTICE.md). The dataset is offered for research/academic use under its publisher's terms; it is not covered by the repository's software license.

## Recorded held-out results

Input identity:

- Official source: https://zenodo.org/records/8196385
- Archive bytes: **57,489,019**
- MD5: `4452953c470f2d95fcb32d5f6e733f7a`
- SHA-256: `d67fd82a711aea0157a9b83175892c6ee60e384a2ddf5bc51f39118453816da8`
- Parsed records: **4,747,963**, including **348,460** alert-tagged records; no records excluded.
- Aggregation: **27,670 occupied, nonoverlapping 60-second UTC windows**. Missing windows are omitted rather than invented or labeled normal.

| Split | Windows | Alert-positive windows | UTC interval, end exclusive |
| --- | ---: | ---: | --- |
| Training | 16,602 | 1,370 | 2005-06-03 22:42 → 2005-10-18 01:37 |
| Validation | 5,534 | 83 | 2005-10-18 01:37 → 2005-11-09 01:26 |
| Test | 5,534 | 385 | 2005-11-09 01:30 → 2006-01-04 16:01 |

The test alert-window prevalence is 385 / 5,534 ≈ **6.96%**. The threshold **0.4597826714634374** maximizes validation F1; ties use higher precision, then a higher threshold. Validation F1 was **0.5641**. The threshold was not chosen from test scores or test labels.

| Held-out test method | Precision | Recall | F1 | Average precision | False positive rate |
| --- | ---: | ---: | ---: | ---: | ---: |
| Scaler + class-balanced logistic regression | 0.7271 | 0.9273 | 0.8151 | 0.8160 | 0.0260 |
| Any ERROR/FATAL/FAILURE/SEVERE severity | 0.5653 | 1.0000 | 0.7223 | 0.5653 | 0.0575 |
| Always non-alert | Undefined | 0.0000 | 0.0000 | 0.0696 | 0.0000 |

The model produced **357 true positives, 134 false positives, 5,015 true negatives and 28 false negatives**. The severity rule produced **385 true positives and 296 false positives**, with no false negatives on this test split. The trained model trades some recall for fewer false positives. Its improvement on this split does not establish a universal advantage or cross-system generalization.

Average precision evaluates score ranking over all thresholds. A constant-score non-alert baseline has AP equal to positive prevalence. Precision is undefined when nothing is predicted positive; recall is undefined when no positives exist. Undefined metrics are JSON `null`, not fabricated numbers. ROC AUC and AP are reported as null when the evaluation has only one class.

## Method and leakage controls

1. Parse the first token solely as the evaluation target: `-` means non-alert; every other tag means alert. A normal-tagged line may contain “error” or have `FATAL` severity; the target is never inferred from keywords or severity.
2. Bucket records by Unix timestamp into fixed 60-second windows. A window is alert-positive if any record has an alert tag. Valid metadata-only records preserve an empty message. Malformed input fails explicitly rather than silently dropping rows.
3. Sort occupied windows chronologically and split by window count: earliest 60% training, next 20% validation, final 20% test. Windows do not overlap and cannot cross split boundaries.
4. Construct eight features: log event/error/fatal/warning counts, log distinct component count, mean/max message length and failure-keyword fraction. The alert token, Unix timestamp, date, machine identifiers and label category text never enter the feature vector.
5. Fit `StandardScaler` and class-balanced `LogisticRegression` using training windows only. Fit no transform on validation or test. Choose the threshold on validation only; evaluate test once for the recorded configuration.
6. Compare the model with a fixed severity heuristic and an always-non-alert baseline on the identical test windows.

The classifier's `predict_proba` output is used as a **0–1 uncalibrated score**. It is not an empirically calibrated probability that an operational incident will occur. In particular, class weighting changes the fitted class distribution. The project does not claim probability calibration.

Repeated templates and temporally adjacent windows can appear on both sides of a cutoff. A chronological split reduces random-split leakage but does not eliminate template overlap, label-policy limitations or temporal dependence. No embargo or template-disjoint evaluation is claimed. The BGL labels concern historical alert categories, not verified outages.

## Score supplied logs

Only load a `model.joblib` generated locally by this pipeline or another trusted source: joblib uses Python pickle serialization and loading an untrusted file can execute code.

The unlabeled input format is BGL with the first alert-tag column omitted:

```text
1117838570 2005.06.03 R02-M1-N0-C:J12-U11 2005-06-03-15.42.50.675872 R02-M1-N0-C:J12-U11 RAS KERNEL INFO instruction cache parity error corrected
```

```bash
.venv/bin/python -m ml.pipeline score \
  --input /path/to/unlabeled.log \
  --model artifacts/model.joblib \
  --output artifacts/scored.json
```

Use `--labeled` only if input retains the original first-column BGL tags and you want metrics against those tags. Scoring reuses the existing scaler, model and threshold; it does not refit or retune. User-supplied score results are not held-out benchmark results. The output separates `total_windows` from `exported_windows`; at most 10,000 evenly spaced chronological windows are exported, and labeled evaluation uses every input window.

## Dashboard contract

`report.status` is `ready` for a successful real run. Without artifacts the serving application returns `not_ready`; it must not invent metrics. All metric rates are 0–1; `threshold` uses the same scale as `score`. `split.train`, `.validation` and `.test` each have `{windows, anomalous_windows, start, end}` with UTC timestamps and exclusive ends.

Each event has `{timestamp, window_start, score, predicted_anomaly, actual_anomaly, messages, log_count}`. `messages` is a string array containing the first three unique, truncated source excerpts collected for that window. These previews are not necessarily the records that triggered the alert label or model score, and are not root-cause explanations. `actual_anomaly` is null when scoring unlabeled records. Dashboard examples are uniformly spaced by chronological index; they are not a top-score selection. The JSON also reports the total and exported window counts.

The coefficient list describes the linear classifier in standardized feature space. Signs describe associations in this fitted model, not causal explanations of failures.

## Tests

Unit/integration tests use explicitly synthetic temporary fixtures solely to test code. Those fixtures never supply the committed evaluation. Checks cover label/content separation, exclusion of tag/time/node data from features, real empty-message handling, invalid input, nonoverlapping temporal partitions, known confusion counts, undefined metrics, validation-only threshold selection, training-only scaler statistics, single-class training failure and unlabeled scoring without invented ground truth.
