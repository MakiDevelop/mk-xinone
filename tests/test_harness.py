from __future__ import annotations

from pathlib import Path

from mk_xinone.backends.base import SeatRequest, SeatResult
from mk_xinone.harness import check_done_gate, check_no_self_accept
from mk_xinone.orchestrator import run_council
from mk_xinone.presets import load_preset


def test_no_self_accept_same_seat():
    # accept_requires points at executor → only one seat → missing reviewer path
    preset_bad = {
        "harness": {"no_self_accept": True, "accept_requires": "executor"},
        "seats": [{"id": "executor"}],
    }
    r = check_no_self_accept(preset_bad, {"executor": {"id": "executor"}}, {"executor": "x"})
    assert not r.ok


def test_done_gate_reviewer_fail():
    preset = {
        "harness": {
            "require_verdict": True,
            "no_self_accept": True,
            "accept_requires": "reviewer",
        },
        "seats": [
            {"id": "executor"},
            {"id": "reviewer"},
            {"id": "synthesizer", "kind": "synthesizer"},
        ],
    }
    seats = {
        "executor": {"id": "executor", "status": "done", "one_line_verdict": "done"},
        "reviewer": {
            "id": "reviewer",
            "status": "done",
            "one_line_verdict": "reject",
            "verdict": "FAIL",
        },
        "synthesizer": {"id": "synthesizer", "status": "done", "one_line_verdict": "x"},
    }
    synth = {"verdict_label": "NO"}
    r = check_done_gate(preset, seats, synthesis=synth, terminal_status_ok=True)
    assert not r.ok
    assert r.code == "REVIEWER_FAIL"


def test_done_gate_pass():
    preset = {
        "harness": {
            "require_verdict": True,
            "no_self_accept": True,
            "accept_requires": "reviewer",
        },
        "seats": [
            {"id": "executor"},
            {"id": "reviewer"},
        ],
    }
    seats = {
        "executor": {"id": "executor", "status": "done", "one_line_verdict": "done"},
        "reviewer": {
            "id": "reviewer",
            "status": "done",
            "one_line_verdict": "ok",
            "verdict": "PASS",
            "evidence": ["tests green"],
        },
    }
    r = check_done_gate(
        preset, seats, synthesis={"verdict_label": "SHIP"}, terminal_status_ok=True
    )
    assert r.ok


class _ScriptedRunner:
    name = "scripted"

    def __init__(self, mapping: dict[str, SeatResult]):
        self.mapping = mapping

    def run_seat(self, request: SeatRequest) -> SeatResult:
        return self.mapping[request.seat_id]


def test_dual_review_blocked_on_fail(tmp_path: Path):
    preset = load_preset("dual-review")

    def ok_worker(sid, role, verdict=None):
        p = {
            "schema": "mk-xinone.seat.v1",
            "id": sid,
            "role": role,
            "status": "done",
            "one_line_verdict": f"{role} says hi",
            "key_points": ["k"],
            "risks": [],
            "confidence": 4,
        }
        if verdict:
            p["verdict"] = verdict
            p["evidence"] = ["e"]
        return SeatResult(ok=True, payload=p, log="ok\n", actor=f"script:{sid}")

    runner = _ScriptedRunner(
        {
            "executor": ok_worker("executor", "Executor"),
            "reviewer": ok_worker("reviewer", "Reviewer", verdict="FAIL"),
            "synthesizer": ok_worker("synthesizer", "Synthesizer"),
        }
    )
    path = run_council(
        "dual review fail case",
        preset,
        backend="openai",
        out_dir=tmp_path / "dr",
        runner=runner,
    )
    meta = (path / "meta.json").read_text(encoding="utf-8")
    assert '"status": "blocked"' in meta or '"status": "failed"' in meta
    assert "completed" not in meta.split("status")[1][:30] or '"status": "blocked"' in meta
