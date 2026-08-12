"""Read and write session directories."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(text: str, max_len: int = 40) -> str:
    s = text.lower().strip()
    s = re.sub(r"https?://\S+", "url", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "run"
    # Prefer ascii-ish slug for paths; fall back if pure CJK
    ascii_s = re.sub(r"[^a-z0-9-]+", "", s)
    if len(ascii_s) >= 3:
        s = ascii_s
    else:
        s = "run"
    return s[:max_len].rstrip("-")


def new_session_id(goal: str) -> str:
    day = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    return f"{day}-{slugify(goal)}"


def read_session(session_dir: Path) -> dict[str, Any]:
    session_dir = session_dir.resolve()
    if not session_dir.is_dir():
        raise FileNotFoundError(f"session not found: {session_dir}")
    meta_path = session_dir / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"missing meta.json in {session_dir}")
    meta = load_json(meta_path)
    seats: dict[str, Any] = {}
    seats_dir = session_dir / "seats"
    if seats_dir.is_dir():
        for p in sorted(seats_dir.glob("*.json")):
            seats[p.stem] = load_json(p)
    synthesis = None
    if (session_dir / "synthesis.json").is_file():
        synthesis = load_json(session_dir / "synthesis.json")
    verdict = None
    if (session_dir / "verdict.md").is_file():
        verdict = (session_dir / "verdict.md").read_text(encoding="utf-8")
    return {
        "dir": session_dir,
        "meta": meta,
        "seats": seats,
        "synthesis": synthesis,
        "verdict_md": verdict,
    }


def format_session_show(bundle: dict[str, Any]) -> str:
    meta = bundle["meta"]
    lines: list[str] = []
    lines.append(f"session: {meta.get('id', bundle['dir'].name)}")
    lines.append(f"preset:  {meta.get('preset', '?')}")
    lines.append(f"status:  {meta.get('status', '?')}")
    lines.append("")
    lines.append("seats:")
    for seat in meta.get("seats") or []:
        sid = seat.get("id", "?")
        role = seat.get("role", sid)
        status = seat.get("status", "?")
        detail = bundle["seats"].get(sid) or {}
        one = detail.get("one_line_verdict", "")
        lines.append(f"  [{status:8}] {role} ({sid})")
        if one:
            lines.append(f"             → {one}")
    lines.append("")
    synth = bundle.get("synthesis") or {}
    if synth:
        lines.append(f"verdict: {synth.get('verdict_label', '?')}  confidence={synth.get('confidence', '?')}")
        consensus = synth.get("consensus") or []
        if consensus:
            lines.append("consensus:")
            for c in consensus[:5]:
                lines.append(f"  - {c}")
        disag = synth.get("disagreements") or []
        if disag:
            lines.append("disagreements:")
            for d in disag[:5]:
                lines.append(f"  - {d.get('topic', '')}: {d.get('summary', '')}")
    lines.append("")
    lines.append(f"path: {bundle['dir']}")
    if bundle.get("verdict_md"):
        lines.append("")
        lines.append("--- verdict.md ---")
        lines.append(bundle["verdict_md"].rstrip())
    return "\n".join(lines) + "\n"
