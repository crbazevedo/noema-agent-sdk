"""Three increasingly proactive journeys; the same tools work in every backend."""

import argparse
import asyncio
import json

from .domain import Tools


def backend(name):
    if name == "noema":
        from .noema_agent import NoemaLesson

        return NoemaLesson
    if name == "adk":
        from .adk_agent import ADKLesson

        return ADKLesson
    if name == "langgraph":
        from .langgraph_agent import LangGraphLesson

        return LangGraphLesson
    raise ValueError(name)


async def run_lesson(framework="noema", level=1):
    tools = Tools({"design:v1": "Compare two interface alternatives"})
    agent = await backend(framework)(level, tools).start()
    try:
        await agent.tick(now=4)
        assert not tools.calls, "Too early: remaining quiet is part of proactivity"
        if level == 1:
            await agent.tick(now=5)
            await agent.tick(now=6)
            assert len(tools.notices) == 1
            assert [c["tool"] for c in tools.calls] == ["notify"]
        elif level == 2:
            tools.notes.clear()
            await agent.tick(now=5)
            assert not tools.notices, "An unavailable note must not become a made-up brief"
            tools.notes["design:v1"] = "Compare two interface alternatives"
            await agent.tick(now=6, quiet=True)
            assert not tools.notices, "Preparation can be useful without an interruption"
            assert (await agent.world())["drafts"]
            await agent.tick(now=7, quiet=False)
            assert len(tools.notices) == 1
        elif level == 3:
            tools.notes["review:v1"] = "Review the release checklist"
            await agent.tick(
                now=5,
                quiet=True,
                meetings={
                    "review": {"start": 9, "revision": 1, "importance": 9},
                },
            )
            assert tools.calls[0]["version"] == "review:v1", "Higher value is prepared first"
            assert not tools.notices
            await agent.tick(
                now=6,
                meetings={
                    "design": {"start": 20, "revision": 2, "importance": 5},
                    "review": {"start": 9, "revision": 1, "importance": 9, "cancelled": True},
                },
            )
            await agent.tick(now=7, quiet=False)
            assert not tools.notices, "Previously prepared work is now obsolete"
            tools.notes["design:v2"] = "The rescheduled meeting has a new agenda"
            await agent.tick(now=15, enabled=False)
            assert not tools.notices, "A standing instruction can be stopped"
            await agent.tick(now=16, enabled=True)
            assert [n["version"] for n in tools.notices] == ["design:v2"]
        else:
            raise ValueError("level must be 1, 2 or 3")
        world = await agent.world()
        return {
            "framework": framework,
            "level": level,
            "calls": tools.calls,
            "notices": tools.notices,
            "world": world,
            "trace": await agent.trace(),
        }
    finally:
        await agent.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=("noema", "adk", "langgraph"), default="noema")
    parser.add_argument("--level", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--trace", action="store_true")
    args = parser.parse_args()
    result = asyncio.run(run_lesson(args.framework, args.level))
    if not args.trace:
        del result["trace"]
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
