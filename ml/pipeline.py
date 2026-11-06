"""Historical classification of fixed BGL windows, without label/time/node features."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import re
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SOURCE_URL = "https://zenodo.org/records/8196385"
FEATURE_NAMES = [
    "log_event_count", "log_error_count", "log_fatal_count", "log_warning_count",
    "log_distinct_components", "mean_message_length", "max_message_length", "failure_keyword_fraction",
]
FAILURE_WORDS = re.compile(r"\b(?:fail(?:ed|ure)?|fatal|exception|panic)\b", re.IGNORECASE)
SEVERE = frozenset({"ERROR", "FATAL", "FAILURE", "SEVERE"})


@dataclass(frozen=True)
class Record:
    timestamp: int
    component: str
    severity: str
    message: str
    alert: bool | None


def parse_bgl(line: str, *, labeled: bool = True) -> Record:
    """Unlabeled scoring input omits the first alert-tag column entirely."""
    fields = line.rstrip("\r\n").split(maxsplit=9 if labeled else 8)
    expected = 10 if labeled else 9
    if len(fields) == expected - 1:
        # The real full corpus contains valid metadata-only records with empty content.
        fields.append("")
    if len(fields) != expected:
        raise ValueError(f"Expected {expected - 1} BGL metadata fields and optional message content.")
    offset = 1 if labeled else 0
    try:
        timestamp = int(fields[offset])
        datetime.fromtimestamp(timestamp, timezone.utc)
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("Invalid Unix timestamp in BGL record.") from exc
    # Alert tag, timestamps and machine identifiers never enter feature construction.
    return Record(timestamp, fields[offset + 6], fields[offset + 7], fields[offset + 8], fields[0] != "-" if labeled else None)


@dataclass
class Window:
    start: int
    count: int = 0
    errors: int = 0
    fatals: int = 0
    warnings: int = 0
    components: set = field(default_factory=set)
    message_lengths: int = 0
    max_message_length: int = 0
    failure_keywords: int = 0
    actual_anomaly: bool = False
    messages: list = field(default_factory=list)

    def add(self, record: Record):
        self.count += 1
        self.errors += record.severity in {"ERROR", "FAILURE", "SEVERE"}
        self.fatals += record.severity == "FATAL"
        self.warnings += record.severity in {"WARN", "WARNING"}
        self.components.add(record.component)
        self.message_lengths += len(record.message)
        self.max_message_length = max(self.max_message_length, len(record.message))
        self.failure_keywords += bool(FAILURE_WORDS.search(record.message))
        self.actual_anomaly |= bool(record.alert)
        excerpt = f"{record.component} {record.severity}: {record.message[:240]}"
        if len(self.messages) < 3 and excerpt not in self.messages:
            self.messages.append(excerpt)

    def features(self):
        return [math.log1p(self.count), math.log1p(self.errors), math.log1p(self.fatals),
                math.log1p(self.warnings), math.log1p(len(self.components)),
                self.message_lengths / self.count, self.max_message_length,
                self.failure_keywords / self.count]

    @property
    def baseline(self):
        return self.errors + self.fatals > 0


def source_lines(path: Path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            candidates = [name for name in archive.namelist() if Path(name).name == "BGL.log"]
            if len(candidates) != 1:
                raise ValueError("Archive must contain exactly one BGL.log.")
            # Stream a known member; never extract untrusted archive paths.
            with archive.open(candidates[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8", errors="strict") as text:
                yield from text
    else:
        with path.open(encoding="utf-8", errors="strict") as text:
            yield from text


def aggregate(path: Path, window_seconds: int = 60, *, labeled: bool = True):
    if window_seconds < 1 or window_seconds > 86_400:
        raise ValueError("Window seconds must be between 1 and 86400.")
    windows = {}
    rows = 0
    alerts = 0
    for line_number, line in enumerate(source_lines(path), start=1):
        try:
            record = parse_bgl(line, labeled=labeled)
        except ValueError as exc:
            raise ValueError(f"Line {line_number}: {exc}") from exc
        bucket = record.timestamp // window_seconds * window_seconds
        if bucket not in windows:
            windows[bucket] = Window(bucket)
        windows[bucket].add(record)
        rows += 1
        alerts += bool(record.alert)
    if not rows:
        raise ValueError("Input contains no records.")
    return [windows[key] for key in sorted(windows)], {"records": rows, "alert_records": alerts if labeled else None}


def chronological_split(windows):
    if len(windows) < 15:
        raise ValueError("At least 15 occupied windows are required for a three-way temporal evaluation.")
    train_end, validation_end = int(len(windows) * 0.6), int(len(windows) * 0.8)
    return windows[:train_end], windows[train_end:validation_end], windows[validation_end:]


def arrays(windows):
    return np.asarray([window.features() for window in windows], dtype=float), np.asarray([int(window.actual_anomaly) for window in windows], dtype=int)


def select_threshold(labels, scores):
    if len(np.unique(labels)) < 2:
        return 0.5, "Validation has a single class; threshold fixed at 0.5 rather than tuned."
    precision, recall, thresholds = precision_recall_curve(labels, scores)
    f1 = 2 * precision[:-1] * recall[:-1] / np.maximum(precision[:-1] + recall[:-1], np.finfo(float).eps)
    # Validation only: maximize F1, then precision, then threshold.
    best = max(range(len(thresholds)), key=lambda index: (f1[index], precision[index], thresholds[index]))
    return float(thresholds[best]), "Maximized validation F1; ties use precision, then the higher threshold."


def evaluate(labels, predictions, scores=None):
    labels, predictions = np.asarray(labels, dtype=bool), np.asarray(predictions, dtype=bool)
    tp = int(np.sum(labels & predictions))
    fp = int(np.sum(~labels & predictions))
    tn = int(np.sum(~labels & ~predictions))
    fn = int(np.sum(labels & ~predictions))
    diverse = len(np.unique(labels)) == 2
    return {
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        "average_precision": float(average_precision_score(labels, scores)) if scores is not None and diverse else None,
        "roc_auc": float(roc_auc_score(labels, scores)) if scores is not None and diverse else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "windows": int(len(labels)), "anomalous_windows": int(np.sum(labels)),
    }


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def split_description(windows, seconds):
    return {"windows": len(windows), "anomalous_windows": sum(window.actual_anomaly for window in windows),
            "start": iso(windows[0].start), "end": iso(windows[-1].start + seconds)}


def checksum(path, algorithm="sha256"):
    digest = hashlib.new(algorithm)
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def event_rows(windows, scores, threshold, *, labels=True, limit=500):
    # A deterministic chronological sample of the test period, not top-score cherry-picking.
    if len(windows) <= limit:
        indices = range(len(windows))
    else:
        indices = np.linspace(0, len(windows) - 1, limit, dtype=int)
    return [{"timestamp": iso(windows[index].start), "window_start": iso(windows[index].start),
             "score": float(scores[index]), "predicted_anomaly": bool(scores[index] >= threshold),
             "actual_anomaly": bool(windows[index].actual_anomaly) if labels else None,
             "messages": windows[index].messages, "log_count": windows[index].count}
            for index in indices]


def train(input_path: Path, output: Path, *, scope: str, window_seconds=60):
    started = time.monotonic()
    windows, counts = aggregate(input_path, window_seconds)
    train_windows, validation_windows, test_windows = chronological_split(windows)
    train_x, train_y = arrays(train_windows)
    validation_x, validation_y = arrays(validation_windows)
    test_x, test_y = arrays(test_windows)
    if len(np.unique(train_y)) != 2:
        raise ValueError("Training period has only one label class; no classifier or metrics will be fabricated.")
    model = make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42))
    model.fit(train_x, train_y)
    validation_scores = model.predict_proba(validation_x)[:, 1]
    threshold, threshold_policy = select_threshold(validation_y, validation_scores)
    test_scores = model.predict_proba(test_x)[:, 1]
    validation_result = evaluate(validation_y, validation_scores >= threshold, validation_scores)
    result = evaluate(test_y, test_scores >= threshold, test_scores)
    baseline = evaluate(test_y, [window.baseline for window in test_windows], [int(window.baseline) for window in test_windows])
    majority = evaluate(test_y, np.zeros(len(test_y), dtype=int), np.zeros(len(test_y)))
    feature_weights = [{"feature": feature, "standardized_coefficient": float(weight)} for feature, weight in zip(FEATURE_NAMES, model[-1].coef_[0])]
    report = {
        "schema_version": 1, "status": "ready", "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {"name": "BGL / Loghub", "source_url": SOURCE_URL,
                    "details": scope, "records": counts["records"], "alert_records": counts["alert_records"],
                    "sha256": checksum(input_path), "md5": checksum(input_path, "md5"),
                    "window_seconds": window_seconds, "occupied_windows": len(windows),
                    "label_definition": "First raw token '-' is non-alert; any other tag is alert. A window is positive if any record is alert."},
        "model": {"name": "StandardScaler + class-balanced LogisticRegression", "feature_names": FEATURE_NAMES,
                  "score_semantics": "Uncalibrated classifier score from predict_proba for historical BGL alert windows; not an empirically calibrated probability or operational risk.",
                  "feature_coefficients": feature_weights, "random_state": 42},
        "evaluation": {**result, "threshold": threshold, "threshold_policy": threshold_policy,
                       "baseline_name": "Any ERROR/FATAL/FAILURE/SEVERE message in the window",
                       "baseline_precision": baseline["precision"], "baseline_recall": baseline["recall"], "baseline_f1": baseline["f1"],
                       "test_windows": len(test_windows), "baseline": baseline, "always_normal_baseline": majority,
                       "validation": validation_result},
        "split": {name: split_description(part, window_seconds) for name, part in [("train", train_windows), ("validation", validation_windows), ("test", test_windows)]},
        "runtime": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "numpy": np.__version__, "elapsed_seconds": round(time.monotonic() - started, 3)},
        "limitations": [
            "Historical classification of observed windows; this does not forecast future incidents or demonstrate live monitoring.",
            "Chronological 60/20/20 split over occupied UTC windows only; periods with no logs are omitted, not labeled normal.",
            "The label tag, timestamps and node identifiers are excluded from features; scaler/model fit training only, threshold uses validation only.",
            "Repeated message patterns and adjacent windows may remain across splits. Temporal separation is not proof of cross-system generalization.",
            "Scores are not calibrated risk. Labels describe BGL alert categories rather than independently verified incident impact.",
            "Baseline may outperform the trained model; inspect held-out metrics rather than assuming ML is better.",
            "Events are an evenly spaced chronological sample of at most 500 held-out windows; metrics use all held-out windows.",
        ],
    }
    if counts["records"] < 4_747_963:
        report["limitations"].insert(0, "This run uses a limited source subset, not the complete 4,747,963-record BGL corpus. Results are not full-corpus benchmark claims.")
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "threshold": threshold, "window_seconds": window_seconds, "feature_names": FEATURE_NAMES, "schema_version": 1}, output / "model.joblib")
    write_json(output / "report.json", report)
    events = event_rows(test_windows, test_scores, threshold)
    write_json(output / "events.json", {"schema_version": 1, "scope": "held-out test windows; deterministic evenly spaced chronological sample", "total_windows": len(test_windows), "exported_windows": len(events), "events": events})
    return report


def score(input_path: Path, model_path: Path, output: Path, *, labeled=False):
    saved = joblib.load(model_path)
    if saved.get("schema_version") != 1 or saved.get("feature_names") != FEATURE_NAMES:
        raise ValueError("Model feature schema does not match this pipeline.")
    windows, counts = aggregate(input_path, saved["window_seconds"], labeled=labeled)
    features, labels = arrays(windows)
    scores = saved["model"].predict_proba(features)[:, 1]
    events = event_rows(windows, scores, saved["threshold"], labels=labeled, limit=10_000)
    result = {"schema_version": 1, "scope": "user-supplied historical records; not held-out benchmark data; at most 10000 evenly spaced windows exported",
              "records": counts["records"], "threshold": saved["threshold"],
              "total_windows": len(windows), "exported_windows": len(events), "events": events}
    if labeled:
        result["evaluation"] = evaluate(labels, scores >= saved["threshold"], scores)
    write_json(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    training = commands.add_parser("train", help="Fit and evaluate a chronological BGL classifier.")
    training.add_argument("--input", type=Path, required=True)
    training.add_argument("--output", type=Path, default=Path("artifacts"))
    training.add_argument("--scope", required=True, help="Exact dataset scope shown in the report.")
    training.add_argument("--window-seconds", type=int, default=60)
    scoring = commands.add_parser("score", help="Score supplied records using a locally generated trusted model.")
    scoring.add_argument("--input", type=Path, required=True)
    scoring.add_argument("--model", type=Path, default=Path("artifacts/model.joblib"))
    scoring.add_argument("--output", type=Path, default=Path("artifacts/scored.json"))
    scoring.add_argument("--labeled", action="store_true", help="Input includes first-column BGL alert labels; compute metrics.")
    arguments = parser.parse_args(argv)
    try:
        if arguments.command == "train":
            report = train(arguments.input, arguments.output, scope=arguments.scope, window_seconds=arguments.window_seconds)
            print(json.dumps({"status": report["status"], "dataset_records": report["dataset"]["records"], "evaluation": report["evaluation"], "elapsed_seconds": report["runtime"]["elapsed_seconds"]}))
        else:
            result = score(arguments.input, arguments.model, arguments.output, labeled=arguments.labeled)
            print(json.dumps({"records": result["records"], "total_windows": result["total_windows"], "exported_windows": result["exported_windows"], "output": str(arguments.output)}))
    except (ValueError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(2, f"Pipeline failed: {exc}\n")


if __name__ == "__main__":
    main()
