"""v0 mock orchestrator — same session layout as future real multi-model runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mk_xinone.session_io import new_session_id, write_json


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def run_mock_council(
    goal: str,
    preset: dict[str, Any],
    out_dir: Path | None = None,
    sessions_root: Path | None = None,
) -> Path:
    """Run mock seats and write a complete session directory. Returns session path."""
    if out_dir is None:
        if sessions_root is None:
            raise ValueError("sessions_root required when out_dir is None")
        out_dir = sessions_root / new_session_id(goal)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "seats").mkdir(exist_ok=True)
    (out_dir / "logs").mkdir(exist_ok=True)

    (out_dir / "input.md").write_text(f"# Input\n\n{goal.strip()}\n", encoding="utf-8")

    seat_defs = preset.get("seats") or []
    seat_metas: list[dict[str, str]] = []
    seat_payloads: list[dict[str, Any]] = []

    for i, seat in enumerate(seat_defs):
        sid = str(seat.get("id", f"seat{i}"))
        role = str(seat.get("role", sid))
        mission = str(seat.get("mission", ""))
        one = f"[{role}] 針對目標給出結構化意見（mock）。使命：{mission or '（未填）'}"
        payload = {
            "schema": "mk-xinone.seat.v1",
            "id": sid,
            "role": role,
            "status": "done",
            "one_line_verdict": one[:200],
            "key_points": [
                f"已讀取使用者目標（mock seat {sid}）",
                f"角色使命：{mission}" if mission else "無額外使命",
            ],
            "risks": [
                "本輪為 mock orchestrator，非真實模型輸出",
            ],
            "confidence": 3,
        }
        write_json(out_dir / "seats" / f"{sid}.json", payload)
        (out_dir / "logs" / f"{sid}.log").write_text(
            f"[mock] seat={sid} status=running\n[mock] seat={sid} status=done\n",
            encoding="utf-8",
        )
        seat_metas.append({"id": sid, "role": role, "status": "done"})
        seat_payloads.append(payload)

    # Lightweight synthesis from seat one-liners
    consensus = [p["one_line_verdict"] for p in seat_payloads[:3]]
    synthesis = {
        "schema": "mk-xinone.synthesis.v1",
        "consensus": consensus,
        "disagreements": [],
        "blind_spots": [
            "v0 mock：未接真實多模型；請以 demo session 或後續 backend 為準",
        ],
        "verdict_label": "MOCK_COMPLETE",
        "confidence": 2,
    }
    write_json(out_dir / "synthesis.json", synthesis)

    graph = {
        "schema": "mk-xinone.graph.v1",
        "nodes": [{"id": s["id"], "label": s["role"]} for s in seat_metas],
        "edges": [],
    }
    write_json(out_dir / "graph.json", graph)

    session_id = out_dir.name
    meta = {
        "schema": "mk-xinone.session.meta.v1",
        "id": session_id,
        "preset": str(preset.get("id", "unknown")),
        "status": "completed",
        "created_at": _now_iso(),
        "input_summary": goal.strip()[:120],
        "seats": seat_metas,
        "orchestrator": "mock_v0",
    }
    write_json(out_dir / "meta.json", meta)

    verdict = "\n".join(
        [
            "# 判決卡",
            "",
            f"- **判決**：`{synthesis['verdict_label']}`",
            f"- **信心**：{synthesis['confidence']} / 5",
            f"- **preset**：{preset.get('id')}",
            "",
            "## 一句話",
            "",
            "Mock council 已跑完並寫入本地 session。接上真實 backend 後格式不變。",
            "",
            "## 各席",
            "",
            *[f"- **{p['role']}**：{p['one_line_verdict']}" for p in seat_payloads],
            "",
        ]
    )
    (out_dir / "verdict.md").write_text(verdict, encoding="utf-8")
    (out_dir / "REPORT.md").write_text(
        f"# Report\n\nGoal:\n\n{goal.strip()}\n\nSee seats/ and synthesis.json.\n",
        encoding="utf-8",
    )
    return out_dir
