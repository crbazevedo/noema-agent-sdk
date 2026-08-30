"""Small JSON-Schema boundary validator used by structured cognition.

Noema deliberately avoids embedding a schema framework in its core.  This
validator implements the subset emitted by the SDK's own canonical schemas;
deployments may validate richer external schemas with their preferred library.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class SchemaValidationError(ValueError):
    pass


def validate_json_schema(value: Any, schema: Mapping[str, Any], *, path: str = "$") -> None:
    """Validate *value* against the supported JSON-Schema subset."""

    if "enum" in schema and value not in schema["enum"]:
        raise SchemaValidationError(f"{path}: value is not in the allowed enum")

    expected = schema.get("type")
    if isinstance(expected, Sequence) and not isinstance(expected, str):
        errors: list[str] = []
        for option in expected:
            try:
                validate_json_schema(value, {**schema, "type": option}, path=path)
                return
            except SchemaValidationError as exc:
                errors.append(str(exc))
        raise SchemaValidationError(f"{path}: value did not match any permitted type")

    if expected == "null":
        if value is not None:
            raise SchemaValidationError(f"{path}: expected null")
        return
    if expected == "object":
        if not isinstance(value, Mapping):
            raise SchemaValidationError(f"{path}: expected object")
        properties = schema.get("properties", {})
        required = schema.get("required", ())
        for key in required:
            if key not in value:
                raise SchemaValidationError(f"{path}.{key}: required property is missing")
        if schema.get("additionalProperties") is False:
            unexpected = set(value) - set(properties)
            if unexpected:
                raise SchemaValidationError(
                    f"{path}: unexpected properties: {', '.join(sorted(unexpected))}"
                )
        for key, item in value.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                validate_json_schema(item, child_schema, path=f"{path}.{key}")
        return
    if expected == "array":
        if not isinstance(value, list):
            raise SchemaValidationError(f"{path}: expected array")
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                validate_json_schema(item, item_schema, path=f"{path}[{index}]")
        return
    if expected == "string":
        if not isinstance(value, str):
            raise SchemaValidationError(f"{path}: expected string")
        return
    if expected == "boolean":
        if not isinstance(value, bool):
            raise SchemaValidationError(f"{path}: expected boolean")
        return
    if expected == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise SchemaValidationError(f"{path}: expected integer")
        _validate_number(value, schema, path)
        return
    if expected == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SchemaValidationError(f"{path}: expected number")
        _validate_number(value, schema, path)
        return
    if expected is None:
        return
    raise SchemaValidationError(f"{path}: unsupported schema type {expected!r}")


def _validate_number(value: int | float, schema: Mapping[str, Any], path: str) -> None:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    if minimum is not None and value < minimum:
        raise SchemaValidationError(f"{path}: value is below minimum {minimum}")
    if maximum is not None and value > maximum:
        raise SchemaValidationError(f"{path}: value is above maximum {maximum}")
