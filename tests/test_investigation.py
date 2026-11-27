import copy
import json
import unittest
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from evals.investigations import evaluate_suite, fixture, grade, load_cases
from investigation import InvestigationTools, WindowUnavailable, investigate
from ml.pipeline import FEATURE_NAMES, Record, Window, event_rows


class InvestigationTests(unittest.TestCase):
    def test_export_uses_local_contribution_and_original_source_line(self):
        X = np.zeros((4, len(FEATURE_NAMES)))
        X[:, 2] = [0, 1, 2, 3]
        model = make_pipeline(StandardScaler(), LogisticRegression()).fit(X, [0, 0, 1, 1])
        window = Window(60)
        for n in range(20):
            window.add(Record(61, "KERNEL", "FATAL", "failure", None), 90 + n)
        window.add(Record(62, "APP", "INFO", "longest message", None), 112)
        x = [window.features()]
        score = model.predict_proba(x)[0, 1]
        row = event_rows([window], [score], score, model=model, labels=False)[0]
        trace = row["investigation"]
        self.assertEqual(trace["driver"]["feature"], "log_fatal_count")
        self.assertEqual(trace["driver"]["observed"], 20)
        self.assertAlmostEqual(trace["driver"]["log_odds"] + model[-1].intercept_[0],
                               model.decision_function(x)[0])
        self.assertEqual([r["id"] for r in trace["records"]], ["L90", "L112"])
        self.assertEqual(trace["records"][1]["timestamp"], "1970-01-01T00:01:02Z")
        self.assertIsNone(row["actual_anomaly"])

    def test_window_and_record_scoping(self):
        events = json.loads((Path(__file__).resolve().parents[1] / "artifacts/events.json").read_text())["events"]
        tools = InvestigationTools(events)
        a, b = [e for e in events if e["predicted_anomaly"]][:2]
        with self.assertRaises(LookupError):
            tools.lookup_log_records(a["window_start"], [b["investigation"]["records"][0]["id"]])
        for start in ["absent", next(e["window_start"] for e in events if not e["predicted_anomaly"])]:
            with self.assertRaises(WindowUnavailable):
                investigate(start, tools)
        for event in events:
            if event["predicted_anomaly"]:
                answer = investigate(event["window_start"], tools)
                self.assertTrue(answer["records"])
                self.assertTrue(answer["claims"])

    def test_grader_rejects_invented_cause_wrong_record_and_altered_quote(self):
        case = next(c for c in load_cases() if c["name"] == "two-distinct-operations")
        answer = investigate(case["start"], fixture(case))
        self.assertEqual(grade(case, answer)["supported"], 2)
        wrong = copy.deepcopy(answer)
        wrong["claims"][0]["citations"] = ["L2"]
        self.assertEqual(grade(case, wrong)["supported"], 1)
        wrong["claims"][0]["text"] = "The server lost power."
        self.assertTrue(grade(case, wrong)["invented"])
        wrong = copy.deepcopy(answer)
        wrong["records"][0]["message"] = "a different message"
        self.assertEqual(grade(case, wrong)["supported"], 1)

    def test_benchmark_includes_causal_answers_and_correct_abstentions(self):
        metrics = evaluate_suite()
        self.assertEqual(metrics["invented_cause_per_case"]["numerator"], 0)
        self.assertEqual(metrics["citation_support"]["rate"], 1)
        self.assertEqual(metrics["abstention_on_insufficient"]["rate"], 1)
        self.assertGreaterEqual(metrics["supported_cause_recall"]["numerator"], 8)
        self.assertEqual(metrics["uncited_record_claims"], 0)
