from __future__ import annotations

from mk_xinone.agents import AgentInfo
from mk_xinone.backends.cli_chair import (
    build_cli_chair_command,
    has_cli_chair_recipe,
    run_cli_chair,
)
from mk_xinone.chair import ChatState, reply_as_chair


def test_recipes_cover_four_clis():
    assert has_cli_chair_recipe("claude")
    assert has_cli_chair_recipe("codex")
    assert has_cli_chair_recipe("gemini")
    assert has_cli_chair_recipe("grok")
    assert not has_cli_chair_recipe("agentx")


def test_codex_command_is_read_only_exec():
    argv = build_cli_chair_command("codex", "hello", last_message_path="/tmp/out.txt")
    assert argv[:2] == ["codex", "exec"]
    assert "-s" in argv and "read-only" in argv
    assert "--ephemeral" in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv


def test_run_cli_chair_uses_injected_runner():
    def fake(argv: list[str], timeout: float) -> tuple[int, str, str]:
        assert argv[0] == "grok"
        assert "-p" in argv
        return 0, "嗨，我是 Grok 主席。", ""

    text = run_cli_chair("grok", "嗨", runner=fake)
    assert "Grok" in text


def test_reply_as_chair_cli_does_not_convene():
    agent = AgentInfo(
        id="cli:codex",
        kind="cli",
        label="Codex CLI",
        available=True,
        runnable=False,
        aliases=["codex"],
        chair_capable=True,
    )

    def fake(argv: list[str], timeout: float) -> tuple[int, str, str]:
        if argv[:2] == ["codex", "exec"]:
            path = argv[argv.index("-o") + 1]
            from pathlib import Path

            Path(path).write_text("已聽懂，尚未開會。", encoding="utf-8")
            return 0, "", ""
        raise AssertionError(argv)

    d = reply_as_chair(agent, "嗨", ChatState(), cli_runner=fake)
    assert d.action == "reply"
    assert "尚未開會" in d.message
