import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np

from ml.pipeline import (FEATURE_NAMES, Window, aggregate, arrays, chronological_split,
                         evaluate, parse_bgl, score, select_threshold, train)


def raw(timestamp, *, alert=False, severity="INFO", message="operation completed"):
    return f"{'KERNEL_TAG' if alert else '-'} {timestamp} 2005.06.03 R00 2005-06-03-00.00.00 R00 RAS KERNEL {severity} {message}\n"


class ParserAndWindowTests(unittest.TestCase):
    def test_ground_truth_uses_tag_not_error_words(self):
        normal = parse_bgl(raw(1117838520, message="instruction cache parity error corrected"))
        alert = parse_bgl(raw(1117838520, alert=True, message="routine-looking text"))
        self.assertFalse(normal.alert)
        self.assertTrue(alert.alert)

    def test_label_time_and_node_changes_cannot_change_features(self):
        first, second = Window(0), Window(0)
        first.add(parse_bgl(raw(1117838520, alert=False)))
        second.add(parse_bgl(raw(1117838580, alert=True).replace("R00", "R99")))
        self.assertEqual(first.features(), second.features())
        self.assertNotEqual(first.actual_anomaly, second.actual_anomaly)

    def test_unlabeled_input_has_no_ground_truth(self):
        record = parse_bgl(raw(1117838520).split(" ", 1)[1], labeled=False)
        self.assertIsNone(record.alert)
        self.assertEqual(record.component, "KERNEL")
        self.assertEqual(record.severity, "INFO")

    def test_real_metadata_only_records_preserve_empty_message_and_tag_label(self):
        line = "- 1120866514 2005.07.08 R02 2005-07-08-16.48.34.004234 R02 RAS KERNEL FATAL\n"
        record = parse_bgl(line)
        self.assertEqual(record.message, "")
        self.assertEqual(record.severity, "FATAL")
        self.assertFalse(record.alert)

    def test_malformed_rows_fail_explicitly(self):
        for line in ["", "not a record", raw(1117838520).replace("1117838520", "bad")]:
            with self.subTest(line=line), self.assertRaises(ValueError):
                parse_bgl(line)

    def test_windows_are_nonoverlapping_sorted_and_occupied_only(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "fixture.log"
            source.write_text(raw(120, alert=True) + raw(0) + raw(59), encoding="utf-8")
            windows, counts = aggregate(source, 60)
        self.assertEqual([window.start for window in windows], [0, 120])
        self.assertEqual([window.count for window in windows], [2, 1])
        self.assertEqual([window.actual_anomaly for window in windows], [False, True])
        self.assertEqual(counts, {"records": 3, "alert_records": 1})

    def test_no_overlapping_timestamp_groups_across_splits(self):
        windows = [Window(index * 60) for index in range(20)]
        parts = chronological_split(windows)
        self.assertEqual([len(part) for part in parts], [12, 4, 4])
        self.assertLess(parts[0][-1].start, parts[1][0].start)
        self.assertLess(parts[1][-1].start, parts[2][0].start)
        with self.assertRaises(ValueError):
            chronological_split(windows[:10])


class EvaluationTests(unittest.TestCase):
    def test_known_confusion_and_metrics(self):
        result = evaluate([1, 1, 0, 0], [1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2])
        self.assertEqual(result["confusion_matrix"], {"tp": 1, "fn": 1, "fp": 1, "tn": 1})
        self.assertEqual((result["precision"], result["recall"], result["f1"]), (0.5, 0.5, 0.5))

    def test_undefined_metrics_are_null_not_fabricated(self):
        result = evaluate([0, 0], [0, 0], [0.1, 0.2])
        for metric in ["precision", "recall", "f1", "average_precision", "roc_auc"]:
            self.assertIsNone(result[metric])

    def test_threshold_is_selected_from_validation_scores(self):
        threshold, explanation = select_threshold(np.array([0, 0, 1, 1]), np.array([0.1, 0.4, 0.6, 0.9]))
        self.assertEqual(threshold, 0.6)
        self.assertIn("validation", explanation)
        self.assertEqual(select_threshold(np.array([0, 0]), np.array([0.1, 0.2]))[0], 0.5)

    def test_model_fit_and_scaler_use_training_only_and_scoring_has_no_fake_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "synthetic_test_fixture.log"
            # Deliberately different later message lengths detect a scaler fit on future rows.
            lines = [raw(index * 60, alert=bool(index % 2), severity="FATAL" if index % 2 else "INFO",
                         message="failure" if index % 2 else "ok") for index in range(30)]
            lines[-6:] = [raw(index * 60, alert=bool(index % 2), severity="FATAL" if index % 2 else "INFO", message="x" * 1000) for index in range(24, 30)]
            source.write_text("".join(lines), encoding="utf-8")
            report = train(source, root / "out", scope="Synthetic unit-test fixture, never a benchmark.")
            saved = joblib.load(root / "out" / "model.joblib")
            windows, _ = aggregate(source)
            expected_x, _ = arrays(chronological_split(windows)[0])
            np.testing.assert_allclose(saved["model"][0].mean_, expected_x.mean(axis=0))
            self.assertEqual(saved["feature_names"], FEATURE_NAMES)
            self.assertEqual(report["dataset"]["records"], 30)
            self.assertEqual(report["evaluation"]["test_windows"], 6)
            before = saved["model"][0].mean_.copy()
            unlabeled = root / "unlabeled.log"
            unlabeled.write_text(lines[0].split(" ", 1)[1], encoding="utf-8")
            result = score(unlabeled, root / "out" / "model.joblib", root / "scored.json")
            self.assertIsNone(result["events"][0]["actual_anomaly"])
            self.assertNotIn("evaluation", result)
            np.testing.assert_array_equal(saved["model"][0].mean_, before)
            self.assertEqual(json.loads((root / "out" / "report.json").read_text())["status"], "ready")

    def test_training_single_class_fails_without_output_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "all_normal.log"
            source.write_text("".join(raw(index * 60) for index in range(30)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "only one label class"):
                train(source, Path(directory) / "out", scope="Synthetic fixture.")
            self.assertFalse((Path(directory) / "out" / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
