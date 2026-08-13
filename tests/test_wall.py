from __future__ import annotations

from pathlib import Path

from mk_xinone.backends.base import SeatRequest, SeatResult
from mk_xinone.orchestrator import run_council


class FlakyThenOk:
    name = "flaky"

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    def run_seat(self, request: SeatRequest) -> SeatResult:
        n = self.calls.get(request.seat_id, 0) + 1
        self.calls[request.seat_id] = n
        if request.seat_id == "architect" and n == 1:
            return SeatResult(
                ok=False,
                payload={
                    "schema": "mk-xinone.seat.v1",
                    "id": "architect",
                    "role": "Architect",
                    "status": "failed",
                    "one_line_verdict": "timeout boom",
                    "key_points": [],
                    "risks": [],
                    "confidence": 1,
                },
                log="err\n",
                error="timeout boom",
                actor="flaky:architect",
            )
        return SeatResult(
            ok=True,
            payload={
                "schema": "mk-xinone.seat.v1",
                "id": request.seat_id,
                "role": request.role,
                "status": "done",
                "one_line_verdict": f"{request.role} ok attempt {n}",
                "key_points": ["k"],
                "risks": [],
                "confidence": 3,
                **(
                    {
                        "verdict_label": "OK",
                        "consensus": ["c"],
                        "disagreements": [],
                        "blind_spots": [],
                    }
                    if request.kind == "synthesizer"
                    else {}
                ),
            },
            log="ok\n",
            actor=f"flaky:{request.seat_id}",
        )


class AlwaysFailSame:
    name = "always_fail"

    def run_seat(self, request: SeatRequest) -> SeatResult:
        return SeatResult(
            ok=False,
            payload={
                "schema": "mk-xinone.seat.v1",
                "id": request.seat_id,
                "role": request.role,
                "status": "failed",
                "one_line_verdict": "same error always",
                "key_points": [],
                "risks": [],
                "confidence": 1,
            },
            log="fail\n",
            error="same error always",
            actor=f"fail:{request.seat_id}",
        )


def test_wall_retries_then_succeeds(tmp_path: Path):
    preset = {
        "id": "t",
        "seats": [
            {"id": "architect", "role": "Architect", "mission": "m"},
            {"id": "synthesizer", "role": "Synthesizer", "kind": "synthesizer"},
        ],
        "harness": {"wall_max_retries": 2, "require_verdict": True},
    }
    runner = FlakyThenOk()
    path = run_council(
        "wall retry",
        preset,
        out_dir=tmp_path / "w1",
        runner=runner,
    )
    assert runner.calls["architect"] == 2
    meta = (path / "meta.json").read_text(encoding="utf-8")
    assert '"status": "completed"' in meta


def test_wall_stops_after_two_same_failures(tmp_path: Path):
    preset = {
        "id": "t",
        "seats": [
            {"id": "architect", "role": "Architect"},
            {"id": "synthesizer", "role": "Synthesizer", "kind": "synthesizer"},
        ],
        "harness": {"wall_max_retries": 2, "require_verdict": True},
    }
    path = run_council(
        "wall hard fail",
        preset,
        out_dir=tmp_path / "w2",
        runner=AlwaysFailSame(),
    )
    meta_txt = (path / "meta.json").read_text(encoding="utf-8")
    assert '"status": "completed"' not in meta_txt or '"status": "failed"' in meta_txt
    assert "wall" in meta_txt or "WALL" in (path / "verdict.md").read_text(encoding="utf-8")
