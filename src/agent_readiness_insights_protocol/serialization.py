"""Thin JSON helpers on top of pydantic for symmetry with downstream consumers.

Pydantic v2 already provides `model_dump_json` / `model_validate_json`;
these wrappers exist so the public API doesn't depend on which pydantic
methods callers happen to know.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def to_json(model: BaseModel, *, indent: int | None = None) -> str:
    """Serialise a pydantic model to a JSON string."""
    return model.model_dump_json(indent=indent)


def from_json(model_cls: type[T], data: str | bytes) -> T:
    """Parse a JSON string/bytes into the given pydantic model."""
    return model_cls.model_validate_json(data)


__all__ = ["to_json", "from_json"]
