"""Seat backends: mock and OpenAI-compatible HTTP."""

from __future__ import annotations

from mk_xinone.backends.base import SeatRequest, SeatResult, SeatRunner
from mk_xinone.backends.mock import MockSeatRunner
from mk_xinone.backends.openai_compatible import OpenAICompatibleSeatRunner, resolve_openai_settings


def get_runner(name: str, **kwargs: object) -> SeatRunner:
    key = (name or "mock").strip().lower()
    if key in {"mock", "mock_v0"}:
        return MockSeatRunner()
    if key in {"openai", "openai-compatible", "openai_compatible", "ollama"}:
        return OpenAICompatibleSeatRunner(**kwargs)  # type: ignore[arg-type]
    raise ValueError(f"unknown backend: {name!r} (use mock|openai)")


__all__ = [
    "MockSeatRunner",
    "OpenAICompatibleSeatRunner",
    "SeatRequest",
    "SeatResult",
    "SeatRunner",
    "get_runner",
    "resolve_openai_settings",
]
