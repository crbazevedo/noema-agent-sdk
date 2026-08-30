"""Local-first deployment profiles assembled entirely through adapters."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from .delivery import EventBroker, InboxConsumer, OutboxPublisher
from .events import Event
from .kernel import NoemaKernel
from .store import SQLiteEventStore
from .system import RuntimeService
from .tracing import NullTracer, OpenTelemetryTracer, Tracer


class DeploymentMode(StrEnum):
    EMBEDDED = "embedded"
    DISTRIBUTED = "distributed"


class _BrokerLifecycle:
    def __init__(self, broker: EventBroker) -> None:
        self.broker = broker

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        await self.broker.close()


@dataclass(frozen=True, slots=True)
class Deployment:
    mode: DeploymentMode
    kernel: NoemaKernel
    services: tuple[RuntimeService, ...] = ()
    broker: EventBroker | None = None

    @classmethod
    def distributed_for_testing(
        cls,
        path: str | Path,
        broker: EventBroker,
        *,
        runtime_id: str = "test-runtime",
        tracer: Tracer | None = None,
    ) -> Deployment:
        sqlite_store = SQLiteEventStore(path)
        kernel = NoemaKernel(store=sqlite_store, distributed=True, tracer=tracer)
        publisher = OutboxPublisher(
            sqlite_store,
            broker,
            worker_id=f"{runtime_id}-publisher",
        )
        consumer = InboxConsumer(
            sqlite_store,
            broker,
            lambda event: _ingest(kernel, event),
            consumer_id=runtime_id,
        )
        return cls(
            DeploymentMode.DISTRIBUTED,
            kernel,
            (_BrokerLifecycle(broker), publisher, consumer),
            broker,
        )


async def deployment_from_env(
    environment: Mapping[str, str] | None = None,
) -> Deployment:
    """Build a portable runtime from ``MODE`` and adapter-specific settings."""

    settings = dict(os.environ if environment is None else environment)
    try:
        mode = DeploymentMode(settings.get("MODE", DeploymentMode.EMBEDDED))
    except ValueError as exc:
        raise ValueError("MODE must be 'embedded' or 'distributed'") from exc
    tracer = _tracer_from_env(settings)
    if mode == DeploymentMode.EMBEDDED:
        raw_path = settings.get("NOEMA_SQLITE_PATH", ".noema/noema.sqlite3")
        path = Path(raw_path)
        if raw_path != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        sqlite_store = SQLiteEventStore(raw_path)
        return Deployment(mode, NoemaKernel(store=sqlite_store, tracer=tracer))

    dsn = settings.get("NOEMA_POSTGRES_DSN")
    if not dsn:
        raise ValueError("NOEMA_POSTGRES_DSN is required in distributed mode")
    from .adapters.brokers import NATSBroker
    from .adapters.stores import PostgresEventStore

    postgres_store = await PostgresEventStore.connect(dsn)
    servers = tuple(
        value.strip()
        for value in settings.get("NOEMA_NATS_SERVERS", "nats://127.0.0.1:4222").split(",")
        if value.strip()
    )
    broker = await NATSBroker.connect(servers)
    runtime_id = settings.get("NOEMA_RUNTIME_ID", f"runtime-{uuid4()}")
    kernel = NoemaKernel(store=postgres_store, distributed=True, tracer=tracer)
    publisher = OutboxPublisher(
        postgres_store,
        broker,
        worker_id=f"{runtime_id}-publisher",
    )
    consumer = InboxConsumer(
        postgres_store,
        broker,
        lambda event: _ingest(kernel, event),
        consumer_id=runtime_id,
    )
    return Deployment(
        mode,
        kernel,
        (_BrokerLifecycle(broker), publisher, consumer),
        broker,
    )


async def _ingest(kernel: NoemaKernel, event: Event) -> None:
    await kernel.ingest(event)


def _tracer_from_env(settings: Mapping[str, str]) -> Tracer:
    endpoint = settings.get("NOEMA_OTLP_ENDPOINT")
    if endpoint is None:
        return NullTracer()
    return OpenTelemetryTracer.from_otlp(
        service_name=settings.get("NOEMA_SERVICE_NAME", "noema"),
        endpoint=endpoint,
        insecure=settings.get("NOEMA_OTLP_INSECURE", "false").lower() == "true",
    )
