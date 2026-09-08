"""Equivalent deterministic ADK 2 workflow with session state and routed nodes."""

from google.adk import Context, Workflow
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, InMemorySessionService
from google.genai import types

from .domain import Proposal, admissible, choose, initial_world, observe


class ADKLesson:
    def __init__(self, level, tools, database=None):
        self.level, self.tools = level, tools
        self.events = []
        self.sessions = (
            DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{database}")
            if database
            else InMemorySessionService()
        )

        def select(ctx: Context):
            proposal = choose(ctx.state["world"])
            ctx.state["proposal"] = proposal.payload() if proposal else None
            ctx.route = "act" if proposal else "done"

        def act(ctx: Context):
            proposal = Proposal(**ctx.state["proposal"])
            world = ctx.state["world"]
            if admissible(proposal, world):
                ctx.state["world"] = tools.invoke(proposal, world)
            else:
                ctx.route = "done"

        def complete(ctx: Context):
            return ctx.state["world"]

        workflow = Workflow(
            name="preparation",
            edges=[
                ("START", select),
                (select, {"act": act, "done": complete}),
                (act, select),
            ],
        )
        self.runner = Runner(node=workflow, app_name="proactive", session_service=self.sessions)

    async def start(self):
        existing = await self.sessions.get_session(
            app_name="proactive",
            user_id="synthetic-owner",
            session_id="lesson",
        )
        if existing is None:
            await self.sessions.create_session(
                app_name="proactive",
                user_id="synthetic-owner",
                session_id="lesson",
                state={"world": initial_world(self.level)},
            )
        return self

    async def tick(self, **update):
        world = observe(await self.world(), **update)
        async for event in self.runner.run_async(
            user_id="synthetic-owner",
            session_id="lesson",
            state_delta={"world": world},
            new_message=types.Content(role="user", parts=[types.Part(text="source observation")]),
        ):
            if event.error_message:
                raise RuntimeError(event.error_message)
            self.events.append(event.model_dump(mode="json"))
        return await self.world()

    async def world(self):
        session = await self.sessions.get_session(
            app_name="proactive",
            user_id="synthetic-owner",
            session_id="lesson",
        )
        return session.state["world"]

    async def trace(self):
        return self.events

    async def close(self):
        await self.runner.close()
