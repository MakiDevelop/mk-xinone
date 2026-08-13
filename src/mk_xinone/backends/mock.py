"""Deterministic mock seat runner (watermarked)."""

from __future__ import annotations

from mk_xinone.backends.base import SeatRequest, SeatResult


class MockSeatRunner:
    name = "mock"

    def run_seat(self, request: SeatRequest) -> SeatResult:
        sid = request.seat_id
        role = request.role
        mission = request.mission or "（未填）"
        goal_snip = (request.goal or "").strip().replace("\n", " ")
        if len(goal_snip) > 60:
            goal_snip = goal_snip[:57] + "…"
        goal_snip = goal_snip or "（空目標）"

        if request.kind == "synthesizer":
            peers = request.peer_summaries
            points = [f"{p.get('role')}: {p.get('one_line_verdict', '')[:80]}" for p in peers]
            one = f"[MOCK synthesizer] 針對「{goal_snip}」綜合 {len(peers)} 席（非真實模型）"
            payload = {
                "schema": "mk-xinone.seat.v1",
                "id": sid,
                "role": role,
                "status": "done",
                "one_line_verdict": one,
                "key_points": points[:6] or ["無工作席產出"],
                "risks": ["mock synthesizer — 判決僅供格式示範"],
                "confidence": 2,
                "verdict": "MOCK_COMPLETE",
                "verdict_label": "MOCK_COMPLETE",
                "consensus": [f"已接收使用者輸入：「{goal_snip}」", f"已綜合 {len(peers)} 個工作席（mock）"],
                "disagreements": [],
                "blind_spots": ["mock 無法做真實多模型分歧"],
            }
        else:
            one = f"[MOCK {role}] 收到「{goal_snip}」— 依使命給格式示範。使命：{mission}"
            payload = {
                "schema": "mk-xinone.seat.v1",
                "id": sid,
                "role": role,
                "status": "done",
                "one_line_verdict": one[:240],
                "key_points": [
                    f"使用者輸入：{goal_snip}",
                    f"角色使命：{mission}",
                    f"mock seat id={sid}",
                ],
                "risks": ["本輪為 mock backend，非真實模型輸出"],
                "confidence": 3,
            }
            # dual-review mock: reviewer must carry a PASS for done-gate demos
            if sid == "reviewer" or role.lower() == "reviewer":
                payload["verdict"] = "PASS"
                payload["evidence"] = ["mock evidence: format-only", f"saw goal: {goal_snip}"]
                payload["one_line_verdict"] = (
                    f"[MOCK Reviewer] VERDICT PASS — 已看過「{goal_snip}」"
                )

        log = f"[mock] seat={sid} kind={request.kind} status=done\n"
        return SeatResult(ok=True, payload=payload, log=log, actor=f"mock:{sid}")
