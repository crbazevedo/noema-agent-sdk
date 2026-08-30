"""Persistence adapters."""

from .postgres import PostgresEventStore

__all__ = ["PostgresEventStore"]
