"""Provider-neutral tracing contracts.

The core depends on this tiny protocol rather than OpenTelemetry itself.  The
OpenTelemetry adapter is imported lazily, so embedded Noema remains dependency
free and fully offline.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

TraceAttribute = str | bool | int | float


class Span(Protocol):
    def set_attribute(self, key: str, value: TraceAttribute) -> None: ...

    def record_exception(self, exception: BaseException) -> None: ...


class Tracer(Protocol):
    def span(
        self,
        name: str,
        attributes: Mapping[str, TraceAttribute] | None = None,
    ) -> AbstractAsyncContextManager[Span]: ...


class _NullSpan:
    def set_attribute(self, key: str, value: TraceAttribute) -> None:
        del key, value

    def record_exception(self, exception: BaseException) -> None:
        del exception


class NullTracer:
    """Zero-cost-enough default used by the dependency-free core."""

    @asynccontextmanager
    async def span(
        self,
        name: str,
        attributes: Mapping[str, TraceAttribute] | None = None,
    ) -> AsyncIterator[Span]:
        del name, attributes
        yield _NullSpan()


class _OpenTelemetrySpan:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set_attribute(self, key: str, value: TraceAttribute) -> None:
        self._span.set_attribute(key, value)

    def record_exception(self, exception: BaseException) -> None:
        self._span.record_exception(exception)


class OpenTelemetryTracer:
    """Adapter for an OpenTelemetry tracer.

    Pass an already configured tracer for maximum deployment control, or use
    :meth:`from_otlp` to configure a standard OTLP exporter.
    """

    def __init__(self, tracer: Any | None = None, *, instrumentation_name: str = "noema") -> None:
        if tracer is None:
            try:
                from opentelemetry import trace
            except ImportError as exc:  # pragma: no cover - depends on optional extra
                raise RuntimeError(
                    "OpenTelemetry support requires `pip install 'noema-agent-sdk[otel]'`"
                ) from exc
            tracer = trace.get_tracer(instrumentation_name)
        self._tracer = tracer

    @classmethod
    def from_otlp(
        cls,
        *,
        service_name: str = "noema",
        endpoint: str | None = None,
        insecure: bool = False,
    ) -> OpenTelemetryTracer:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "OTLP support requires `pip install 'noema-agent-sdk[otel]'`"
            ) from exc

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        exporter = (
            OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
            if endpoint is not None
            else OTLPSpanExporter(insecure=insecure)
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        return cls(provider.get_tracer("noema"))

    @asynccontextmanager
    async def span(
        self,
        name: str,
        attributes: Mapping[str, TraceAttribute] | None = None,
    ) -> AsyncIterator[Span]:
        with self._tracer.start_as_current_span(name, attributes=dict(attributes or {})) as span:
            yield _OpenTelemetrySpan(span)
