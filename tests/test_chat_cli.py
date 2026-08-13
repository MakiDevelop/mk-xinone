from __future__ import annotations

from mk_xinone.cli import main


def test_chat_greeting_no_council(monkeypatch, capsys):
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
    assert "session" not in out.lower() or "開會" not in out.split("哈囉")[0]


def test_chat_force_council(monkeypatch, capsys):
    inputs = iter(["/council 評估本地 session 當 SSOT 是否合理", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    try:
        main(["chat", "--backend", "mock"])
    except SystemExit as e:
        assert e.code in {0, 1, 3}
    out = capsys.readouterr().out
    assert "Architect" in out or "seat" in out
    assert "completed" in out or "MOCK" in out
