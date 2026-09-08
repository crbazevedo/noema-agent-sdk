"""Independent-process persistence check at a completed observation boundary.

This does not claim automatic timer rearming, in-flight recovery or exactly-once
external effects. The first process exits without closing its runtime after a
completed tick. The second opens the same framework store and receives a new tick.
"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from .domain import Tools
from .lessons import backend


async def phase(framework, directory, number):
    directory = Path(directory)
    tools = Tools({"design:v1": "Persist this synthetic agenda"})
    agent = await backend(framework)(2, tools, str(directory / "state.sqlite")).start()
    try:
        await agent.tick(now=5 if number == 1 else 6)
        result = {
            "pid": os.getpid(),
            "phase": number,
            "notices": tools.notices,
            "calls": tools.calls,
            "world": await agent.world(),
        }
        with (directory / f"phase-{number}.json").open("w") as stream:
            json.dump(result, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if number == 1:
            os._exit(17)  # Deliberately skip shutdown only in this subprocess probe.
    finally:
        await agent.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("framework", choices=("noema", "adk", "langgraph"))
    parser.add_argument("directory")
    parser.add_argument("phase", type=int, choices=(1, 2))
    args = parser.parse_args()
    asyncio.run(phase(args.framework, args.directory, args.phase))
