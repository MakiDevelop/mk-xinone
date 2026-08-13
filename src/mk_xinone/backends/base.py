"""SeatRunner protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class SeatRequest:
    goal: str
    seat_id: str
    role: str
    mission: str = ""
    kind: str = "worker"  # worker | synthesizer
    peer_summaries: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class SeatResult:
    ok: bool
    payload: dict[str, Any]
    log: str = ""
    error: str | None = None
    actor: str = "unknown"  # identity for no_self_accept checks


class SeatRunner(Protocol):
    name: str

    def run_seat(self, request: SeatRequest) -> SeatResult: ...
