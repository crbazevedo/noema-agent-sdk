"""Equivalent LangGraph with conditional routing and a persistent state option."""

from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from .domain import Proposal, admissible, choose, initial_world, observe


class State(TypedDict):
    world: dict
    proposal: dict | None


class LangGraphLesson:
    def __init__(self, level, tools, database=None):
        self.level, self.tools, self.database = level, tools, database
        self.events = []
        self.config = {"configurable": {"thread_id": "lesson"}, "recursion_limit": 100}

        def select(state):
            proposal = choose(state["world"])
            return {"proposal": proposal.payload() if proposal else None}

        def act(state):
            proposal = Proposal(**state["proposal"])
            if not admissible(proposal, state["world"]):
                return {"proposal": None}
            return {"world": tools.invoke(proposal, state["world"])}

        builder = StateGraph(State)
        builder.add_node("select", select)
        builder.add_node("act", act)
        builder.add_edge(START, "select")
        builder.add_conditional_edges("select", lambda s: "act" if s["proposal"] else END)
        builder.add_edge("act", "select")
        self.builder = builder

    async def start(self):
        if self.database:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            self.connection = AsyncSqliteSaver.from_conn_string(self.database)
            saver = await self.connection.__aenter__()
        else:
            saver = InMemorySaver()
        self.graph = self.builder.compile(checkpointer=saver)
        if not (await self.graph.aget_state(self.config)).values:
            await self.graph.aupdate_state(self.config, {"world": initial_world(self.level)})
        return self

    async def tick(self, **update):
        world = observe(await self.world(), **update)
        async for event in self.graph.astream({"world": world}, self.config, stream_mode="updates"):
            self.events.append(event)
        return await self.world()

    async def world(self):
        return (await self.graph.aget_state(self.config)).values["world"]

    async def trace(self):
        return self.events

    async def close(self):
        if self.database:
            await self.connection.__aexit__(None, None, None)
