from __future__ import annotations

from pathlib import Path

import pytest

from mk_xinone.orchestrator import run_council
from mk_xinone.presets import load_preset
from mk_xinone.session_io import allocate_session_dir, redact_secrets, write_json


def test_allocate_collision_suffix(tmp_path: Path):
    root = tmp_path / "sessions"
    a = allocate_session_dir(root, "hello world collision")
    b = allocate_session_dir(root, "hello world collision")
    assert a != b
    assert a.exists() and b.exists()


def test_refuse_nonempty_out(tmp_path: Path):
    out = tmp_path / "existing"
    out.mkdir()
    (out / "stale.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        allocate_session_dir(None, "g", out_dir=out, force=False)
    # force ok
    p = allocate_session_dir(None, "g", out_dir=out, force=True)
    assert p == out.resolve()


def test_atomic_write_json(tmp_path: Path):
    path = tmp_path / "meta.json"
    write_json(path, {"a": 1})
    assert path.read_text(encoding="utf-8").strip().startswith("{")
    assert not list(tmp_path.glob("*.tmp"))


def test_redact_secrets():
    s = redact_secrets("Authorization: Bearer sk-abc123SECRET")
    assert "sk-abc" not in s
    assert "REDACTED" in s


def test_mock_run_lifecycle_meta(tmp_path: Path):
    preset = load_preset("council-lite")
    path = run_council(
        "lifecycle test goal",
        preset,
        backend="mock",
        out_dir=tmp_path / "run1",
    )
    meta = (path / "meta.json").read_text(encoding="utf-8")
    assert '"status": "completed"' in meta
    assert '"mode": "mock"' in meta
    assert "synthesizer" in meta
