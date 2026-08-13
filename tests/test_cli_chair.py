from __future__ import annotations

from mk_xinone.agents import AgentInfo
from mk_xinone.backends.cli_chair import (
    build_cli_chair_command,
    has_cli_chair_recipe,
    parse_claude_auth_status,
    probe_cli_chair_ready,
    run_cli_chair,
)
from mk_xinone.chair import ChatState, reply_as_chair


def test_recipes_cover_four_clis():
    assert has_cli_chair_recipe("claude")
    assert has_cli_chair_recipe("codex")
    assert has_cli_chair_recipe("gemini")
    assert has_cli_chair_recipe("grok")
    assert not has_cli_chair_recipe("agentx")


def test_claude_command_does_not_use_bare():
    argv = build_cli_chair_command("claude", "hello", session_id="11111111-1111-1111-1111-111111111111")
    assert "--bare" not in argv
    assert "--no-session-persistence" not in argv
    assert "--safe-mode" in argv
    assert "--effort" in argv
    assert "--session-id" in argv
    assert "-p" in argv
    assert "--permission-mode" in argv


def test_claude_continue_uses_resume():
    sid = "11111111-1111-1111-1111-111111111111"
    first = build_cli_chair_command("claude", "hi", session_id=sid)
    again = build_cli_chair_command(
        "claude", "再問一次", continue_session=True, session_id=sid
    )
    assert "--session-id" in first
    assert "--resume" in again
    assert sid in again
    assert "--no-session-persistence" not in again


def test_parse_claude_auth_logged_in():
    ok, reason = parse_claude_auth_status('{"loggedIn": true, "email": "a@b.c"}')
    assert ok is True
    assert reason == ""


def test_parse_claude_auth_logged_out():
    ok, reason = parse_claude_auth_status('{"loggedIn": false}')
    assert ok is False
    assert "claude auth login" in reason


def test_run_cli_chair_treats_login_error_as_failure():
    def fake(argv: list[str], timeout: float) -> tuple[int, str, str]:
        return 0, "Not logged in · Please run /login", ""

    try:
        run_cli_chair("claude", "hi", runner=fake)
    except RuntimeError as exc:
        assert "claude auth login" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_probe_claude_uses_auth_status():
    def fake(argv: list[str], timeout: float) -> tuple[int, str, str]:
        assert argv[:3] == ["claude", "auth", "status"]
        return 0, '{"loggedIn": false}', ""

    ok, reason = probe_cli_chair_ready("claude", runner=fake, use_cache=False)
    assert ok is False
    assert "claude auth login" in reason


def test_codex_command_is_read_only_exec():
    argv = build_cli_chair_command("codex", "hello", last_message_path="/tmp/out.txt")
    assert argv[:2] == ["codex", "exec"]
    assert "-s" in argv and "read-only" in argv
    assert "--ephemeral" not in argv
    assert "--dangerously-bypass-approvals-and-sandbox" not in argv
    cont = build_cli_chair_command(
        "codex", "next", continue_session=True, last_message_path="/tmp/out.txt"
    )
    assert cont[:3] == ["codex", "exec", "resume"]
    assert "--last" in cont


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


def test_reply_as_chair_second_turn_resumes():
    agent = AgentInfo(
        id="cli:claude",
        kind="cli",
        label="Claude Code CLI",
        available=True,
        runnable=False,
        aliases=["claude"],
        chair_capable=True,
    )
    seen: list[list[str]] = []

    def fake(argv: list[str], timeout: float) -> tuple[int, str, str]:
        seen.append(argv)
        return 0, f"ok-{len(seen)}", ""

    state = ChatState()
    first = reply_as_chair(agent, "Hi", state, cli_runner=fake)
    second = reply_as_chair(agent, "還在嗎", state, cli_runner=fake)
    assert first.action == second.action == "reply"
    assert "--session-id" in seen[0]
    assert "--resume" in seen[1]
    assert "--no-session-persistence" not in seen[0]
    assert "還在嗎" in seen[1][-1]
