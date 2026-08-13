from __future__ import annotations

from mk_xinone.cli import main


def test_chat_one_goal_then_quit(monkeypatch, capsys, tmp_path):
    # isolate sessions dir by monkeypatching after import is hard; use mock and quit
    inputs = iter(
        [
            "hello council from chat",
            "/quit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    # run chat with mock backend
    try:
        main(["chat", "--backend", "mock", "--preset", "council-lite"])
    except SystemExit as e:
        assert e.code in {0, 1, 3}
    out = capsys.readouterr().out
    assert "mk-xinone chat" in out
    assert "session" in out.lower() or "MOCK" in out or "status" in out
