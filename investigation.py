"""Offline investigation assistant for the historical BGL classifier."""
import re


class WindowUnavailable(LookupError):
    pass


class InvestigationTools:
    """Read a single events export. Record IDs are source line numbers within that input."""

    def __init__(self, events):
        self._events = {event.get("window_start") or event["timestamp"]: event for event in events}

    def get_flagged_window(self, start):
        event = self._events.get(start)
        if event is None or event.get("predicted_anomaly") is not True:
            raise WindowUnavailable("No exported flagged window at that time.")
        trace = event.get("investigation", {})
        return {"start": start, "score": event["score"], "count": event["log_count"],
                "threshold": trace.get("threshold"), "driver": trace.get("driver"),
                "record_ids": [row["id"] for row in trace.get("records", [])]}

    def lookup_log_records(self, start, record_ids):
        event = self._events.get(start)
        if event is None or event.get("predicted_anomaly") is not True:
            raise WindowUnavailable("No exported flagged window at that time.")
        records = {row["id"]: row for row in event.get("investigation", {}).get("records", [])}
        if any(key not in records for key in record_ids):
            raise LookupError("A record is unavailable in this window.")
        return [dict(records[key]) for key in record_ids]


# Only recognize complete, affirmative BGL diagnostics. Each conclusion is local
# to the named operation, even if many records in the window repeat it.
LOAD = re.compile(r"ciod: Error loading \S+: invalid or missing program image, (Permission denied|No such file or directory)")
CHDIR = re.compile(r"ciod: LOGIN chdir\([^()]+\) failed: (No such file or directory|Input/output error)")
READ_SOCKET = re.compile(r"ciod: Error reading message prefix(?: after LOAD_MESSAGE)? on CioStream socket to [0-9.]+:[0-9]+[:,] (Connection reset by peer|Link has been severed)")
READ_REASONS = {
    "Connection reset by peer": "A socket read failed because the peer reset the connection.",
    "Link has been severed": "A socket read failed because the link had been severed.",
}
LOAD_REASONS = {
    "Permission denied": "A program load failed because access was denied.",
    "No such file or directory": "A program load failed because the named file or path could not be found.",
}
CHDIR_REASONS = {
    "No such file or directory": "A login directory change failed because the named path could not be found.",
    "Input/output error": "A login directory change failed because the system returned an I/O error.",
}
FEATURES = {
    "log_event_count": "event count", "log_error_count": "error count",
    "log_fatal_count": "fatal record count", "log_warning_count": "warning count",
    "log_distinct_components": "number of distinct components",
    "mean_message_length": "average message length", "max_message_length": "longest message length",
    "failure_keyword_fraction": "fraction of messages containing failure keywords",
}


def reported_reason(record):
    if (record["component"], record["severity"]) != ("APP", "FATAL"):
        return None
    for pattern, reasons in ((LOAD, LOAD_REASONS), (CHDIR, CHDIR_REASONS), (READ_SOCKET, READ_REASONS)):
        match = pattern.fullmatch(record["message"])
        if match:
            return reasons[match[1]]
    return None


def investigate(start, tools):
    """Answer 'Why was this window flagged?' using only the two read tools."""
    window = tools.get_flagged_window(start)
    records = tools.lookup_log_records(start, window["record_ids"])
    decision = f"The saved classifier flagged this window with a score of {window['score']:.6g}."
    if window["threshold"] is not None:
        decision += f" The flag threshold was {window['threshold']:.6g} (inclusive)."
    driver = window["driver"]
    if driver:
        observed = (f"{driver['observed']:.2%}" if driver['feature'] == "failure_keyword_fraction"
                    else f"{driver['observed']:.6g}")
        decision += (f" Across all {window['count']} records, {FEATURES[driver['feature']]} "
                     f"({observed}) made the largest "
                     f"positive contribution to the model score (+{driver['log_odds']:.3g} log-odds "
                     "relative to the training mean).")
    findings = {}
    for record in records:
        reason = reported_reason(record)
        if reason:
            findings.setdefault(reason, []).append(record["id"])
    claims = [{"kind": "reported_cause", "text": reason, "citations": ids} for reason, ids in findings.items()]
    if not claims and records:
        record = next((r for r in records if r["severity"] in {"FATAL", "ERROR"}), records[0])
        detail = f"{record['component']} logged a {record['severity']} record"
        detail += f' reading “{record["message"]}”.' if record["message"] else " with an empty message."
        claims.append({"kind": "observation", "text": detail, "citations": [record["id"]]})
    assessment = ("The cited records give an immediate reason for the named operation. "
                  "The wider incident cause is undetermined." if findings else
                  "Insufficient evidence to identify a cause from the available records.")
    return {"window": start, "decision": decision, "claims": claims, "assessment": assessment,
            "records": records, "total_records": window["count"]}
