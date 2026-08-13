"""Read and write session directories (atomic writes, collision-safe ids)."""

from __future__ import annotations

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SECRET_KV_RE = re.compile(
    r"(?i)(api[_-]?key|authorization|token|secret|password)\s*[:=]\s*['\"]?([^\s'\"\\]+)"
)
_BEARER_RE = re.compile(r"(?i)(bearer)\s+(\S+)")
_SK_RE = re.compile(r"\b(sk-[A-Za-z0-9\-_]{6,})\b")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Atomic JSON write: temp file then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp = path.with_name(path.name + f".{secrets.token_hex(4)}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{secrets.token_hex(4)}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def redact_secrets(text: str) -> str:
    """Strip common secret patterns from logs (never write keys to session)."""
    out = _SECRET_KV_RE.sub(r"\1=***REDACTED***", text)
    out = _BEARER_RE.sub(r"\1 ***REDACTED***", out)
    out = _SK_RE.sub("***REDACTED***", out)
    return out



def slugify(text: str, max_len: int = 40) -> str:
    s = text.lower().strip()
    s = re.sub(r"https?://\S+", "url", s)
    s = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = "run"
    ascii_s = re.sub(r"[^a-z0-9-]+", "", s)
    if len(ascii_s) >= 3:
        s = ascii_s
    else:
        s = "run"
    return s[:max_len].rstrip("-")


def new_session_id(goal: str) -> str:
    day = datetime.now(UTC).astimezone().strftime("%Y-%m-%d")
    return f"{day}-{slugify(goal)}"


def allocate_session_dir(
    sessions_root: Path | None,
    goal: str,
    out_dir: Path | None = None,
    *,
    force: bool = False,
) -> Path:
    """
    Create a fresh session directory.

    - Default: sessions_root / <date-slug> with numeric suffix on collision.
    - Explicit out_dir: fail if non-empty unless force=True.
    """
    if out_dir is not None:
        out = out_dir.resolve()
        if out.exists():
            try:
                non_empty = any(out.iterdir())
            except NotADirectoryError as e:
                raise FileExistsError(f"out path is not a directory: {out}") from e
            if non_empty and not force:
                raise FileExistsError(
                    f"session dir not empty (refuse overwrite): {out}\n"
                    "use --force to overwrite or pick a new --out path"
                )
        out.mkdir(parents=True, exist_ok=True)
        return out

    if sessions_root is None:
        raise ValueError("sessions_root required when out_dir is None")
    sessions_root = sessions_root.resolve()
    sessions_root.mkdir(parents=True, exist_ok=True)
    base = new_session_id(goal)
    candidate = sessions_root / base
    if not candidate.exists():
        candidate.mkdir(parents=True)
        return candidate
    for i in range(2, 1000):
        c = sessions_root / f"{base}-{i}"
        if not c.exists():
            c.mkdir(parents=True)
            return c
    raise RuntimeError(f"could not allocate session dir under {sessions_root}")


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


def format_session_show(bundle: dict[str, Any], *, verbose: bool = False) -> str:
    meta = bundle["meta"]
    lines: list[str] = []
    orch = meta.get("orchestrator") or meta.get("backend") or "?"
    mode = meta.get("mode", "?")
    lines.append(f"session: {meta.get('id', bundle['dir'].name)}")
    lines.append(f"preset:  {meta.get('preset', '?')}")
    lines.append(f"status:  {meta.get('status', '?')}")
    lines.append(f"mode:    {mode}  backend={orch}")
    if mode == "mock" or str(orch).startswith("mock"):
        lines.append("note:    *** MOCK — not a real multi-model council ***")
    lines.append("")
    lines.append("seats:")
    for seat in meta.get("seats") or []:
        sid = seat.get("id", "?")
        role = seat.get("role", sid)
        status = seat.get("status", "?")
        detail = bundle["seats"].get(sid) or {}
        one = detail.get("one_line_verdict", "")
        lines.append(f"  [{status:8}] {role} ({sid})")
        if one and (verbose or status == "done"):
            # default: one line only; verbose later expands more
            short = one if len(one) <= 100 else one[:97] + "..."
            lines.append(f"             → {short}")
    lines.append("")
    synth = bundle.get("synthesis") or {}
    if synth:
        lines.append(
            f"verdict: {synth.get('verdict_label', '?')}  "
            f"confidence={synth.get('confidence', '?')}"
        )
        consensus = synth.get("consensus") or []
        if consensus:
            lines.append("consensus:")
            for c in consensus[:3 if not verbose else 8]:
                lines.append(f"  - {c}")
        disag = synth.get("disagreements") or []
        if disag:
            lines.append("disagreements:")
            for d in disag[:3 if not verbose else 8]:
                lines.append(f"  - {d.get('topic', '')}: {d.get('summary', '')}")
    lines.append("")
    lines.append(f"path: {bundle['dir']}")
    if verbose and bundle.get("verdict_md"):
        lines.append("")
        lines.append("--- verdict.md ---")
        lines.append(bundle["verdict_md"].rstrip())
    elif not verbose:
        lines.append("(use --verbose for full verdict.md / more detail)")
    return "\n".join(lines) + "\n"
