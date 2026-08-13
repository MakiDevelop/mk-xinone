"""Harness gates: done-gate and no_self_accept (M1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HarnessResult:
    ok: bool
    code: str
    message: str


def _reviewer_verdict(payload: dict[str, Any]) -> str | None:
    v = payload.get("verdict") or payload.get("verdict_label")
    if isinstance(v, str) and v.strip():
        return v.strip().upper()
    # scan one_line / key_points
    blob = " ".join(
        [
            str(payload.get("one_line_verdict") or ""),
            " ".join(str(x) for x in (payload.get("key_points") or [])),
        ]
    ).upper()
    for token in ("PASS_WITH_NITS", "PASS", "FAIL"):
        if token in blob:
            return token
    return None


def check_no_self_accept(
    preset: dict[str, Any],
    seat_results: dict[str, dict[str, Any]],
    actors: dict[str, str],
) -> HarnessResult:
    """Reject when dual-review harness requires distinct reviewer."""
    harness = preset.get("harness") or {}
    if not harness.get("no_self_accept"):
        return HarnessResult(True, "SKIP", "no_self_accept not required")

    accept = harness.get("accept_requires") or "reviewer"
    executor_id = "executor"
    reviewer_id = str(accept)

    if executor_id not in seat_results or reviewer_id not in seat_results:
        # also allow first two non-synthesizer seats
        workers = [
            s["id"]
            for s in (preset.get("seats") or [])
            if s.get("kind") != "synthesizer"
        ]
        if len(workers) >= 2:
            executor_id, reviewer_id = workers[0], workers[1]
        else:
            return HarnessResult(
                False,
                "NO_SELF_ACCEPT_MISSING",
                "no_self_accept requires executor and reviewer seats",
            )

    if executor_id == reviewer_id:
        return HarnessResult(
            False,
            "NO_SELF_ACCEPT_SAME_SEAT",
            "executor and reviewer must be different seats",
        )

    a_ex = actors.get(executor_id, "")
    a_rv = actors.get(reviewer_id, "")
    # Same seat id already blocked; also block identical actor string when both mock-forced equal
    # For real OpenAI same model is OK (different roles); only block if actor encodes seat id
    if a_ex and a_rv and a_ex == a_rv and a_ex.startswith("mock:") is False:
        # same model endpoint is allowed for dual-review (independent prompts)
        pass
    # Hard rule: reviewer payload must not claim to be executor
    rev = seat_results.get(reviewer_id) or {}
    if rev.get("id") == executor_id:
        return HarnessResult(
            False,
            "NO_SELF_ACCEPT_ID_COLLISION",
            "reviewer payload id collides with executor",
        )

    return HarnessResult(True, "OK", "no_self_accept passed")


def check_done_gate(
    preset: dict[str, Any],
    seat_results: dict[str, dict[str, Any]],
    *,
    synthesis: dict[str, Any] | None,
    terminal_status_ok: bool,
) -> HarnessResult:
    """Require seats done, optional verdict, dual-review reviewer PASS."""
    harness = preset.get("harness") or {}
    seats_def = preset.get("seats") or []

    if not terminal_status_ok:
        return HarnessResult(False, "SEATS_NOT_OK", "one or more seats failed")

    for s in seats_def:
        sid = s["id"]
        payload = seat_results.get(sid)
        if not payload:
            return HarnessResult(False, "MISSING_SEAT", f"missing seat output: {sid}")
        if payload.get("status") == "failed":
            return HarnessResult(False, "SEAT_FAILED", f"seat failed: {sid}")

    if harness.get("require_verdict") and (
        not synthesis or not synthesis.get("verdict_label")
    ):
        return HarnessResult(False, "MISSING_VERDICT", "require_verdict: no verdict_label")


    if harness.get("no_self_accept") or harness.get("accept_requires"):
        accept = str(harness.get("accept_requires") or "reviewer")
        rev = seat_results.get(accept)
        if not rev:
            return HarnessResult(False, "MISSING_REVIEWER", f"missing reviewer seat: {accept}")
        verdict = _reviewer_verdict(rev)
        if verdict is None:
            return HarnessResult(
                False,
                "REVIEWER_NO_VERDICT",
                "reviewer did not produce PASS/FAIL verdict",
            )
        if verdict == "FAIL":
            return HarnessResult(
                False,
                "REVIEWER_FAIL",
                "reviewer verdict is FAIL — cannot complete",
            )
        if verdict not in {"PASS", "PASS_WITH_NITS"}:
            return HarnessResult(
                False,
                "REVIEWER_BAD_VERDICT",
                f"reviewer verdict not acceptable: {verdict}",
            )

    return HarnessResult(True, "OK", "done-gate passed")
