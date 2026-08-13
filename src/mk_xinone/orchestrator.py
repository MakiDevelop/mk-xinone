"""Council orchestrator: lifecycle + backends + harness."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mk_xinone.backends import SeatRequest, get_runner
from mk_xinone.backends.base import SeatRunner
from mk_xinone.harness import check_done_gate, check_no_self_accept
from mk_xinone.session_io import (
    allocate_session_dir,
    redact_secrets,
    write_json,
    write_text,
)

ProgressCb = Callable[[str], None]


def _now_iso() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


def _emit(cb: ProgressCb | None, msg: str) -> None:
    if cb:
        cb(msg)


def _split_seats(preset: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    workers: list[dict[str, Any]] = []
    synths: list[dict[str, Any]] = []
    for s in preset.get("seats") or []:
        if s.get("kind") == "synthesizer" or s.get("id") == "synthesizer":
            synths.append(s)
        else:
            workers.append(s)
    return workers, synths


def _build_synthesis_from_seats(
    workers: list[dict[str, Any]],
    synth_payload: dict[str, Any] | None,
    *,
    mode: str,
) -> dict[str, Any]:
    if synth_payload and (
        synth_payload.get("consensus")
        or synth_payload.get("verdict_label")
        or synth_payload.get("verdict")
    ):
        return {
            "schema": "mk-xinone.synthesis.v1",
            "consensus": list(synth_payload.get("consensus") or [])
            or [synth_payload.get("one_line_verdict", "")],
            "disagreements": list(synth_payload.get("disagreements") or []),
            "blind_spots": list(synth_payload.get("blind_spots") or []),
            "verdict_label": str(
                synth_payload.get("verdict_label")
                or synth_payload.get("verdict")
                or ("MOCK_COMPLETE" if mode == "mock" else "COMPLETE")
            ),
            "confidence": int(synth_payload.get("confidence") or 3),
        }
    # Fallback fold worker one-liners
    return {
        "schema": "mk-xinone.synthesis.v1",
        "consensus": [w.get("one_line_verdict", "") for w in workers if w.get("one_line_verdict")],
        "disagreements": [],
        "blind_spots": (
            ["mock run — not a real multi-model council"]
            if mode == "mock"
            else ["no synthesizer structured fields; folded from workers"]
        ),
        "verdict_label": "MOCK_COMPLETE" if mode == "mock" else "COMPLETE",
        "confidence": 2 if mode == "mock" else 3,
    }


def run_council(
    goal: str,
    preset: dict[str, Any],
    *,
    backend: str = "mock",
    out_dir: Path | None = None,
    sessions_root: Path | None = None,
    force: bool = False,
    on_progress: ProgressCb | None = None,
    runner: SeatRunner | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> Path:
    """
    Run a council and write a session directory.

    Lifecycle: allocate → meta.running → seats → harness → completed|failed|blocked.
    Never marks completed if harness fails.
    """
    out = allocate_session_dir(sessions_root, goal, out_dir, force=force)
    seats_path = out / "seats"
    logs_path = out / "logs"
    seats_path.mkdir(exist_ok=True)
    logs_path.mkdir(exist_ok=True)

    session_id = out.name
    mode = "mock" if (backend or "mock").lower().startswith("mock") else "real"
    if runner is None:
        runner = get_runner(
            backend,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    backend_name = getattr(runner, "name", backend)

    workers_def, synths_def = _split_seats(preset)
    all_defs = list(workers_def) + list(synths_def)

    seat_meta: list[dict[str, str]] = [
        {"id": str(s["id"]), "role": str(s.get("role", s["id"])), "status": "pending"}
        for s in all_defs
    ]

    def _meta(status: str, **extra: Any) -> dict[str, Any]:
        m: dict[str, Any] = {
            "schema": "mk-xinone.session.meta.v1",
            "id": session_id,
            "preset": str(preset.get("id", "unknown")),
            "status": status,
            "mode": mode,
            "created_at": _now_iso(),
            "input_summary": goal.strip()[:120],
            "seats": seat_meta,
            "orchestrator": backend_name,
            "backend": backend_name,
        }
        m.update(extra)
        return m

    write_text(out / "input.md", f"# Input\n\n{goal.strip()}\n")
    write_json(out / "meta.json", _meta("running"))
    _emit(on_progress, f"session {session_id} status=running mode={mode}")

    seat_payloads: dict[str, dict[str, Any]] = {}
    actors: dict[str, str] = {}
    any_failed = False
    wall_hits: list[dict[str, Any]] = []
    harness_cfg = preset.get("harness") or {}
    # wall_max_retries: max attempts per seat (default 2 = try + one retry)
    max_attempts = int(harness_cfg.get("wall_max_retries") or 2)
    max_attempts = max(1, min(max_attempts, 5))

    def _set_status(sid: str, status: str) -> None:
        for row in seat_meta:
            if row["id"] == sid:
                row["status"] = status
                break

    def _run_seat_with_wall(
        sdef: dict[str, Any],
        *,
        kind: str,
        peer_summaries: list[dict[str, Any]] | None = None,
    ) -> bool:
        """Run seat with wall retries. Returns True if seat succeeded."""
        nonlocal any_failed
        sid = str(sdef["id"])
        role = str(sdef.get("role", sid))
        log_chunks: list[str] = []
        last_err_key = ""
        same_err_streak = 0

        for attempt in range(1, max_attempts + 1):
            _set_status(sid, "running")
            write_json(out / "meta.json", _meta("running"))
            suffix = f" attempt {attempt}/{max_attempts}" if max_attempts > 1 else ""
            _emit(on_progress, f"seat {role} ({sid}) running…{suffix}")

            result = runner.run_seat(
                SeatRequest(
                    goal=goal,
                    seat_id=sid,
                    role=role,
                    mission=str(sdef.get("mission", "")),
                    kind=kind,
                    peer_summaries=list(peer_summaries or []),
                )
            )
            log_chunks.append(
                redact_secrets(f"--- attempt {attempt}/{max_attempts} ---\n{result.log or ''}")
            )
            actors[sid] = result.actor
            payload = result.payload
            seat_payloads[sid] = payload
            write_json(seats_path / f"{sid}.json", payload)
            write_text(logs_path / f"{sid}.log", "".join(log_chunks))

            ok = result.ok and payload.get("status") != "failed"
            if ok:
                _set_status(sid, "done")
                _emit(on_progress, f"seat {role} ({sid}) done")
                write_json(out / "meta.json", _meta("running"))
                return True

            err_key = (result.error or payload.get("one_line_verdict") or "failed")[:200]
            if err_key == last_err_key:
                same_err_streak += 1
            else:
                same_err_streak = 1
                last_err_key = err_key

            # Wall: same error twice, or exhausted attempts
            hit_wall = same_err_streak >= 2 or attempt >= max_attempts
            if hit_wall:
                any_failed = True
                _set_status(sid, "failed")
                wall_hits.append(
                    {
                        "seat": sid,
                        "attempts": attempt,
                        "error": err_key,
                        "same_error_streak": same_err_streak,
                    }
                )
                gap = (
                    f"WALL seat={sid}: same/exhausted failure after {attempt} attempt(s); "
                    f"error={err_key[:120]}"
                )
                _emit(on_progress, f"seat {role} ({sid}) WALL — {gap}")
                write_json(out / "meta.json", _meta("running"))
                return False

            _emit(
                on_progress,
                f"seat {role} ({sid}) failed attempt {attempt}, retrying…",
            )

        any_failed = True
        _set_status(sid, "failed")
        write_json(out / "meta.json", _meta("running"))
        return False

    # --- workers ---
    for sdef in workers_def:
        _run_seat_with_wall(sdef, kind="worker")

    # --- synthesizer (explicit) ---
    synth_payload: dict[str, Any] | None = None
    peer_summaries = [
        {
            "id": sid,
            "role": seat_payloads[sid].get("role", sid),
            "one_line_verdict": seat_payloads[sid].get("one_line_verdict", ""),
            "key_points": seat_payloads[sid].get("key_points", []),
            "risks": seat_payloads[sid].get("risks", []),
            "confidence": seat_payloads[sid].get("confidence"),
            "verdict": seat_payloads[sid].get("verdict"),
        }
        for sid in seat_payloads
    ]

    for sdef in synths_def:
        ok = _run_seat_with_wall(
            sdef, kind="synthesizer", peer_summaries=peer_summaries
        )
        if ok:
            synth_payload = seat_payloads.get(str(sdef["id"]))

    synthesis = _build_synthesis_from_seats(
        [seat_payloads[s["id"]] for s in workers_def if s["id"] in seat_payloads],
        synth_payload,
        mode=mode,
    )
    write_json(out / "synthesis.json", synthesis)

    graph = {
        "schema": "mk-xinone.graph.v1",
        "nodes": [{"id": r["id"], "label": r["role"]} for r in seat_meta],
        "edges": [],
    }
    # light edges from disagreements
    for d in synthesis.get("disagreements") or []:
        if d.get("a") and d.get("b"):
            graph["edges"].append(
                {"source": d["a"], "target": d["b"], "label": d.get("topic", "disagrees")}
            )
    write_json(out / "graph.json", graph)

    # --- harness ---
    ns = check_no_self_accept(preset, seat_payloads, actors)
    dg = check_done_gate(
        preset,
        seat_payloads,
        synthesis=synthesis,
        terminal_status_ok=not any_failed,
    )

    final_status = "completed"
    harness_note = ""
    if not ns.ok:
        final_status = "blocked"
        harness_note = f"{ns.code}: {ns.message}"
        _emit(on_progress, f"harness BLOCKED {harness_note}")
    elif not dg.ok:
        if dg.code == "REVIEWER_FAIL":
            final_status = "blocked"
        elif any_failed or dg.code in {"SEATS_NOT_OK", "SEAT_FAILED"}:
            final_status = "failed"
        else:
            final_status = "blocked"
        harness_note = f"{dg.code}: {dg.message}"
        _emit(on_progress, f"harness {final_status.upper()} {harness_note}")
    else:
        _emit(on_progress, "harness done-gate OK")

    # If harness failed, do NOT claim completed even if seats look fine
    extra: dict[str, Any] = {}
    if harness_note:
        extra["harness"] = {"ok": final_status == "completed", "detail": harness_note}
    if wall_hits:
        extra["wall"] = wall_hits
        gap_line = "; ".join(
            f"{h['seat']}×{h['attempts']}:{str(h.get('error', ''))[:60]}" for h in wall_hits
        )
        extra["system_gap"] = f"wall → retry exhausted → review backend/prompt ({gap_line})"

    write_json(out / "meta.json", _meta(final_status, **extra))

    verdict_lines = [
        "# 判決卡",
        "",
        f"- **狀態**：`{final_status}`",
        f"- **判決**：`{synthesis.get('verdict_label')}`",
        f"- **信心**：{synthesis.get('confidence')} / 5",
        f"- **preset**：{preset.get('id')}",
        f"- **mode**：{mode} / backend={backend_name}",
        "",
    ]
    if mode == "mock":
        verdict_lines += [
            "> **MOCK 浮水印**：本輪非真實多模型 council。",
            "",
        ]
    if harness_note:
        verdict_lines += [f"> Harness: {harness_note}", ""]
    if wall_hits:
        verdict_lines += [
            f"> Wall: {len(wall_hits)} seat(s) exhausted retries (max={max_attempts})",
            "",
        ]
    verdict_lines += ["## 各席", ""]
    for sdef in all_defs:
        sid = str(sdef["id"])
        p = seat_payloads.get(sid) or {}
        verdict_lines.append(
            f"- **{p.get('role', sid)}** [{p.get('status', '?')}]: "
            f"{p.get('one_line_verdict', '')}"
        )
    verdict_lines.append("")
    write_text(out / "verdict.md", "\n".join(verdict_lines))
    write_text(
        out / "REPORT.md",
        f"# Report\n\nGoal:\n\n{goal.strip()}\n\n"
        f"status={final_status} mode={mode}\n\nSee seats/ and synthesis.json.\n",
    )

    _emit(on_progress, f"session {session_id} status={final_status}")
    return out


# Back-compat name used by older tests/CLI
def run_mock_council(
    goal: str,
    preset: dict[str, Any],
    out_dir: Path | None = None,
    sessions_root: Path | None = None,
    *,
    force: bool = False,
    on_progress: ProgressCb | None = None,
) -> Path:
    return run_council(
        goal,
        preset,
        backend="mock",
        out_dir=out_dir,
        sessions_root=sessions_root,
        force=force,
        on_progress=on_progress,
    )
