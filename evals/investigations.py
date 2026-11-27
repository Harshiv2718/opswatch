"""Run the fixed OpsWatch investigation benchmark: python -m evals.investigations."""
import json
from pathlib import Path

from investigation import InvestigationTools, investigate

ROOT = Path(__file__).resolve().parents[1]


def load_cases():
    return json.loads((ROOT / "evals/investigation_cases.json").read_text())


def fixture(case):
    event = {"window_start": case["start"], "predicted_anomaly": True, "score": 0.75,
             "log_count": max(1, len(case["records"])), "messages": ["Unattributed preview."]}
    if not case.get("legacy"):
        event["investigation"] = {"threshold": 0.75, "driver": None, "records": case["records"]}
    return InvestigationTools([event])


def observation_text(record):
    prefix = f'{record["component"]} logged a {record["severity"]} record'
    if not record["message"]:
        return prefix + " with an empty message."
    return prefix + f' reading “{record["message"]}”.'


def grade(case, answer):
    # Gold records are pinned independently of the event export used at runtime.
    gold = {r["id"]: r for r in case["records"]}
    returned = {r["id"]: r for r in answer["records"]}
    supported = citations = uncited = 0
    invented = False
    found_causes = set()
    for claim in answer["claims"]:
        text = claim["text"]
        ids = claim["citations"]
        if claim["kind"] == "reported_cause":
            allowed = case["causes"].get(text, [])
            if not allowed:
                invented = True
        elif claim["kind"] == "observation":
            allowed = [key for key, r in gold.items() if observation_text(r) == text]
        else:
            raise ValueError(f'Unexpected claim kind: {claim["kind"]}')
        uncited += not ids
        citations += len(ids)
        matches = [key in allowed and key in gold and gold[key] == returned.get(key)
                   and answer["window"] == case["start"] for key in ids]
        supported += sum(matches)
        if claim["kind"] == "reported_cause" and any(matches):
            found_causes.add(text)
    asserted = any(c["kind"] == "reported_cause" for c in answer["claims"])
    return {"case": case["name"], "citations": citations, "supported": supported, "uncited": uncited,
            "invented": invented, "abstained": not asserted, "gold_causes": len(case["causes"]),
            "found_causes": len(found_causes), "claims": len(answer["claims"])}


def evaluate_suite():
    events = json.loads((ROOT / "artifacts/events.json").read_text())["events"]
    tools = InvestigationTools(events)
    results = []
    for case in load_cases():
        source = fixture(case) if case.get("synthetic") else tools
        results.append(grade(case, investigate(case["start"], source)))
    def metric(numerator, denominator):
        return {"numerator": numerator, "denominator": denominator,
                "rate": numerator / denominator if denominator else None}
    negatives = [r for r in results if r["gold_causes"] == 0]
    return {
        "citation_support": metric(sum(r["supported"] for r in results), sum(r["citations"] for r in results)),
        "invented_cause_per_case": metric(sum(r["invented"] for r in results), len(results)),
        "abstention_on_insufficient": metric(sum(r["abstained"] for r in negatives), len(negatives)),
        "supported_cause_recall": metric(sum(r["found_causes"] for r in results), sum(r["gold_causes"] for r in results)),
        "uncited_record_claims": sum(r["uncited"] for r in results), "cases": results,
    }


if __name__ == "__main__":
    print(json.dumps(evaluate_suite(), indent=2))
