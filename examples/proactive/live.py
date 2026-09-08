"""A finite clock host: source updates wake the agent without another prompt."""

import argparse
import asyncio

from .domain import Tools
from .lessons import backend


async def run_clock(framework="noema", interval=1.0):
    """Ten synthetic minutes; interval controls demo speed, not business policy."""
    if interval <= 0:
        raise ValueError("interval must be positive")
    tools = Tools({"design:v1": "Agree on the interface"})
    agent = await backend(framework)(2, tools).start()
    try:
        for minute in range(1, 11):
            await asyncio.sleep(interval)
            await agent.tick(now=minute)
        assert len(tools.notices) == 1
        assert tools.notices[0]["at"] == 5
        return tools.notices
    finally:
        await agent.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=("noema", "adk", "langgraph"), default="noema")
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args()
    print(asyncio.run(run_clock(args.framework, args.interval)))
