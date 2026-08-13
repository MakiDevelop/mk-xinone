from __future__ import annotations

from mk_xinone.agents import AgentInfo, DiscoveryResult
from mk_xinone.cli import main


def _stub_discover():
    mock = AgentInfo(
        id="mock",
        kind="mock",
        label="Mock",
        available=True,
        runnable=True,
        model="mock",
        aliases=["mock"],
        chair_capable=True,
    )
    return DiscoveryResult(agents=[mock], runnable=[mock], notes=["test stub"])


def test_chat_greeting_no_council(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("mk_xinone.cli.discover_agents", _stub_discover)
    monkeypatch.setattr("mk_xinone.cli.sessions_dir", lambda: tmp_path)
    monkeypatch.setattr("mk_xinone.cli.warmup_chair", lambda *a, **k: (True, "skip"))
    inputs = iter(["哈囉～", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    try:
        main(["chat", "--backend", "mock"])
    except SystemExit as e:
        assert e.code in {0, 1, 3}
    out = capsys.readouterr().out
    assert "主席" in out
    # Must NOT run full multi-seat progress for greeting
    assert "seat Architect" not in out
    assert "開會確認" not in out


def test_chat_force_council(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("mk_xinone.cli.discover_agents", _stub_discover)
    monkeypatch.setattr("mk_xinone.cli.sessions_dir", lambda: tmp_path)
    monkeypatch.setattr("mk_xinone.cli.warmup_chair", lambda *a, **k: (True, "skip"))
    # Force fixed preset path (only mock → no real all-hands)
    inputs = iter(["/council 評估本地 session 當 SSOT 是否合理", "", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    try:
        main(["chat", "--backend", "mock", "--no-all-agents"])
    except SystemExit as e:
        assert e.code in {0, 1, 3}
    out = capsys.readouterr().out
    assert "開會確認" in out
    assert "Architect" in out or "seat" in out
    assert "completed" in out or "MOCK" in out
