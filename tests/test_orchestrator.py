from __future__ import annotations

from pathlib import Path

from mk_xinone.orchestrator import run_mock_council
from mk_xinone.presets import load_preset
from mk_xinone.session_io import read_session


def test_mock_run(tmp_path: Path):
    preset = load_preset("council-lite")
    out = tmp_path / "test-run"
    path = run_mock_council("evaluate local sessions as SSOT", preset, out_dir=out)
    assert path == out.resolve()
    bundle = read_session(path)
    assert bundle["meta"]["status"] == "completed"
    # council-lite: architect + analyst + engineer + synthesizer
    assert len(bundle["seats"]) == 4
    assert "synthesizer" in bundle["seats"]
    assert (path / "verdict.md").is_file()
