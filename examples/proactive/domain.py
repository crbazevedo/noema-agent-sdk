"""Shared teaching problem and tiny tools, independent of every agent framework.

Time is an integer minute on a synthetic timeline. These are explicit standing
instructions, not discovered preferences. All framework comparisons reuse this
file, and its code is included in the maintained-code inventory.
"""

from copy import deepcopy
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Proposal:
    tool: str
    meeting: str
    revision: int
    value: float
    reason: str

    @property
    def key(self):
        return f"{self.tool}:{self.meeting}:v{self.revision}"

    def payload(self):
        return asdict(self)


def initial_world(level=1):
    return {
        "level": level,
        "now": 0,
        "enabled": True,
        "quiet": False,
        "meetings": {"design": {"start": 10, "revision": 1, "importance": 5}},
        "notes": {},
        "reads": {},
        "drafts": {},
        "notified": [],
    }


def proposals(world):
    """Anticipate a preparation gap; do nothing outside the useful window."""
    if not world["enabled"]:
        return []
    candidates = []
    for name, meeting in world["meetings"].items():
        remaining = meeting["start"] - world["now"]
        revision = meeting["revision"]
        version = f"{name}:v{revision}"
        if meeting.get("cancelled") or not 0 < remaining <= 5:
            continue
        if version in world["notified"]:
            continue
        if world["level"] == 1:
            tool, reason = "notify", "Preparation is due before the meeting"
        elif version not in world["notes"]:
            if world["reads"].get(version) == world["now"]:
                continue  # Unavailable evidence is not evidence of absence.
            tool, reason = "read_note", "Resolve a missing preparation fact"
        elif version not in world["drafts"]:
            tool, reason = "prepare_brief", "Prepare from the current note"
        else:
            tool, reason = "notify", "A current brief is ready before the meeting"
        if tool == "notify" and world["quiet"]:
            continue  # This tutorial mandate explicitly permits deferral.
        candidates.append(Proposal(tool, name, revision, meeting["importance"], reason))
    return candidates


def choose(world):
    """Equivalent fixed-cost ranking for the ADK/LangGraph examples."""
    candidates = proposals(world)
    return max(candidates, key=lambda item: item.value, default=None)


def admissible(proposal, world):
    """A small product rule, not a general permission or distributed CAS system."""
    meeting = world["meetings"].get(proposal.meeting)
    return bool(
        world["enabled"]
        and meeting
        and not meeting.get("cancelled")
        and meeting["revision"] == proposal.revision
        and 0 < meeting["start"] - world["now"] <= 5
        and not (proposal.tool == "notify" and world["quiet"])
    )


class Tools:
    """Three local tools. A separate ledger observes calls and notice effects."""

    def __init__(self, notes=None):
        self.notes = notes or {}
        self.calls = []
        self.notices = []

    def invoke(self, proposal, world):
        updated = deepcopy(world)
        version = f"{proposal.meeting}:v{proposal.revision}"
        self.calls.append({"tool": proposal.tool, "version": version, "at": world["now"]})
        if proposal.tool == "read_note":
            updated["reads"][version] = world["now"]
            if version in self.notes:
                updated["notes"][version] = self.notes[version]
        elif proposal.tool == "prepare_brief":
            updated["drafts"][version] = f"Brief: {world['notes'][version]}"
        elif proposal.tool == "notify":
            text = world["drafts"].get(version, "Prepare for your upcoming meeting")
            self.notices.append({"version": version, "at": world["now"], "text": text})
            updated["notified"].append(version)
        else:
            raise ValueError(f"Unknown tool: {proposal.tool}")
        return updated


def observe(world, *, now, meetings=None, enabled=None, quiet=None):
    """Apply a synthetic trusted source/control update; never a user chat turn."""
    if now < world["now"]:
        raise ValueError("The teaching clock cannot move backwards")
    updated = deepcopy(world)
    updated["now"] = now
    if meetings is not None:
        updated["meetings"].update(deepcopy(meetings))
    if enabled is not None:
        updated["enabled"] = enabled
    if quiet is not None:
        updated["quiet"] = quiet
    return updated
