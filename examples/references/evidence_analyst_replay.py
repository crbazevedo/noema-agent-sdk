"""Read-only projection from recorded events; imports no runtime or capabilities."""

import argparse
import json
from pathlib import Path


def project(events, through_sequence=None):
    state = {
        "goal_revision": None,
        "goal_status": None,
        "memory_conflicts": 0,
        "timer_fired": False,
        "selected_activity_ids": [],
        "deferred_activity_ids": [],
        "bridge_admissions": 0,
        "source_reads": 0,
        "staged_artifacts": [],
        "current_artifact": None,
        "last_boundary": None,
    }
    for event in events:
        seq = event.get("sequence")
        if through_sequence is not None and (seq is None or seq > through_sequence):
            continue
        kind = event["type"]
        p = event["payload"]
        if kind == "intent.goal_revision_recorded":
            state["goal_revision"] = p["revision_id"]
            state["goal_status"] = p["status"]
            current = state["current_artifact"]
            if current and current["goal_revision"] != p["revision_id"]:
                state["current_artifact"] = None
        elif kind == "memory.contradiction_detected":
            state["memory_conflicts"] += 1
        elif kind == "reference.timer_fired":
            state["timer_fired"] = True
        elif kind == "reference.selection_observed":
            state["selected_activity_ids"] = p["selected"]
            state["deferred_activity_ids"] = p["deferred"]
        elif kind == "reference.bridge_admitted":
            state["bridge_admissions"] += 1
        elif kind == "reference.source_read":
            state["source_reads"] += 1
        elif kind == "reference.artifacts_staged":
            state["staged_artifacts"] = p["artifacts"]
        elif kind == "reference.current_artifact_published":
            state["current_artifact"] = p
        elif kind in {
            "reference.preparation_discarded",
            "reference.preparation_failed",
            "reference.bridge_rejected",
            "reference.scan_suppressed",
            "reference.scan_no_selection",
            "reference.wake_suppressed",
        }:
            state["last_boundary"] = {"event_type": kind, "payload": p}
    return state


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("trace", type=Path)
    parser.add_argument("--through", type=int)
    args = parser.parse_args()
    print(
        json.dumps(
            project(json.loads(args.trace.read_text())["events"], args.through),
            indent=2,
            sort_keys=True,
        )
    )
