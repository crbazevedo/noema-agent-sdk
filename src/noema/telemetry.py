"""Small async telemetry sinks. Event history remains the canonical trace."""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .types import utc_now


@dataclass(frozen=True, slots=True)
class Metric:
    name: str
    value: float
    tags: Mapping[str, str] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: utc_now().isoformat())


class TelemetrySink(Protocol):
    async def record(self, metric: Metric) -> None: ...

    async def close(self) -> None: ...


class InMemoryTelemetry:
    def __init__(self) -> None:
        self.metrics: list[Metric] = []
        self.counters: Counter[str] = Counter()
        self._lock = asyncio.Lock()

    async def record(self, metric: Metric) -> None:
        async with self._lock:
            self.metrics.append(metric)
            self.counters[metric.name] += metric.value

    async def close(self) -> None:
        return None


class JsonlTelemetry:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._closed = False

    async def record(self, metric: Metric) -> None:
        if self._closed:
            raise RuntimeError("telemetry sink is closed")
        line = json.dumps(
            {
                "name": metric.name,
                "value": metric.value,
                "tags": dict(metric.tags),
                "timestamp": metric.timestamp,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        async with self._lock:
            await asyncio.to_thread(self._append, line)

    def _append(self, line: str) -> None:
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")

    async def close(self) -> None:
        self._closed = True
