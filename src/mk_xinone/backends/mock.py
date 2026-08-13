"""Deterministic mock seat runner (watermarked)."""

from __future__ import annotations

from mk_xinone.backends.base import SeatRequest, SeatResult


class MockSeatRunner:
    name = "mock"

    def run_seat(self, request: SeatRequest) -> SeatResult:
        sid = request.seat_id
        role = request.role
        mission = request.mission or "（未填）"
        if request.kind == "synthesizer":
            peers = request.peer_summaries
            points = [f"{p.get('role')}: {p.get('one_line_verdict', '')[:80]}" for p in peers]
            one = f"[MOCK synthesizer] 綜合 {len(peers)} 席（非真實模型）"
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
            }
        else:
            one = f"[MOCK {role}] 針對目標給出結構化意見。使命：{mission}"
            payload = {
                "schema": "mk-xinone.seat.v1",
                "id": sid,
                "role": role,
                "status": "done",
                "one_line_verdict": one[:200],
                "key_points": [
                    f"已讀取使用者目標（mock seat {sid}）",
                    f"角色使命：{mission}",
                ],
                "risks": ["本輪為 mock backend，非真實模型輸出"],
                "confidence": 3,
            }
            # dual-review mock: reviewer must carry a PASS for done-gate demos
            if sid == "reviewer" or role.lower() == "reviewer":
                payload["verdict"] = "PASS"
                payload["evidence"] = ["mock evidence: format-only"]
                payload["one_line_verdict"] = f"[MOCK Reviewer] VERDICT PASS — {mission[:80]}"

        log = f"[mock] seat={sid} kind={request.kind} status=done\n"
        return SeatResult(ok=True, payload=payload, log=log, actor=f"mock:{sid}")
