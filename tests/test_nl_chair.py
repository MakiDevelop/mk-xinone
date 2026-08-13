"""§10 NL chair acceptance — table-driven, mock-only, sessions → tmp_path."""

from __future__ import annotations

from pathlib import Path

import pytest

from mk_xinone.agents import (
    AgentInfo,
    DiscoveryResult,
    pick_default_chair_agent,
    resolve_agent_ref,
)
from mk_xinone.chair import (
    ChairAssignment,
    ChatState,
    parse_confirm_reply,
    parse_intent,
)
from mk_xinone.cli import _default_to_chat, main
from mk_xinone.session_io import latest_session, list_sessions, write_json

# ---------------------------------------------------------------------------
# §10 intent table
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "primary", "checks"),
    [
        ("嗨，先跟你聊聊。", "reply", {"convene": False, "stay_chat_only": False}),
        (
            "先不要開會，幫我整理三點。",
            "reply",
            {"stay_chat_only": True, "convene": False},
        ),
        (
            "召集大家開會，評估本地 session 當 SSOT。",
            "convene",
            {"goal_has": "session", "convene": True},
        ),
        (
            "請多個 agent 比較方案 A 和 B。",
            "convene",
            {"goal_has": "方案", "convene": True},
        ),
        ("開個會。", "clarify", {"convene": False, "has_question": True}),
        (
            "讓 Codex 當主席。",
            "reply",
            {"chair_change": "appoint", "chair_ref": "Codex", "convene": False},
        ),
        (
            "你來當主席，召集大家評估這份提案。",
            "convene",
            {"chair_change": "appoint", "you": True, "goal_has": "提案"},
        ),
        (
            "不要讓 Codex 當主席了，恢復預設。",
            "reply",
            {"chair_change": "revoke", "convene": False},
        ),
        (
            "現在有哪些 agent？誰能當主席？",
            "list_agents",
            {"convene": False},
        ),
        (
            "顯示上一場會議結果。",
            "show_last_session",
            {"convene": False},
        ),
    ],
)
def test_section10_intent_table(text: str, primary: str, checks: dict) -> None:
    plan = parse_intent(text)
    assert plan.primary == primary
    if checks.get("convene"):
        assert plan.primary == "convene"
        assert plan.goal
    elif checks.get("convene") is False:
        assert plan.primary != "convene"
    if "stay_chat_only" in checks:
        assert plan.stay_chat_only is checks["stay_chat_only"]
    if "goal_has" in checks:
        assert plan.goal and checks["goal_has"] in plan.goal
    if "chair_change" in checks:
        assert plan.chair_change == checks["chair_change"]
    if "chair_ref" in checks:
        assert plan.chair_ref and checks["chair_ref"].lower() in plan.chair_ref.lower()
    if checks.get("you"):
        assert plan.chair_change == "appoint"
        assert plan.chair_ref is None
    if checks.get("has_question"):
        assert plan.question


def test_negative_eval_without_collective_is_not_convene() -> None:
    plan = parse_intent("幫我評估 X 的風險")
    assert plan.primary != "convene"
    assert plan.primary == "reply"


def test_negative_contradiction_asks_one_question() -> None:
    plan = parse_intent("不要開會，但召集大家評估 X")
    assert plan.primary == "clarify"
    assert plan.question
    assert plan.goal is None or plan.primary != "convene"


def test_confirm_replies() -> None:
    assert parse_confirm_reply("") == "confirm"
    assert parse_confirm_reply("y") == "confirm"
    assert parse_confirm_reply("Y") == "confirm"
    assert parse_confirm_reply("是") == "confirm"
    assert parse_confirm_reply("開") == "confirm"
    assert parse_confirm_reply("n") == "cancel"
    assert parse_confirm_reply("取消") == "cancel"
    assert parse_confirm_reply("不要") == "cancel"
    assert parse_confirm_reply("讓 Gemini 當主席") == "appoint"
    assert parse_confirm_reply("那先幫我整理一下") == "chatter"


# ---------------------------------------------------------------------------
# agents: resolve / default chair / ambiguity
# ---------------------------------------------------------------------------


def _qwen(n: str, model: str) -> AgentInfo:
    return AgentInfo(
        id=f"ollama:{n}",
        kind="ollama",
        label=f"Ollama/{model}",
        available=True,
        runnable=True,
        model=model,
        aliases=["qwen", n, model, model.split(":")[0]],
        chair_capable=True,
    )


def test_resolve_qwen_ambiguous_does_not_pick_first() -> None:
    agents = [_qwen("qwen3_8b", "qwen3:8b"), _qwen("qwen2_7b", "qwen2:7b")]
    result = resolve_agent_ref("qwen", agents, for_chair=True)
    assert result.status == "ambiguous"
    assert result.agent is None
    assert len(result.candidates) == 2


def test_resolve_codex_not_capable() -> None:
    agents = [
        AgentInfo(
            id="cli:codex",
            kind="cli",
            label="Codex CLI",
            available=True,
            runnable=False,
            aliases=["codex"],
            chair_capable=False,
            chair_unavailable_reason="尚無 chair adapter（P1）",
        )
    ]
    result = resolve_agent_ref("Codex", agents, for_chair=True)
    assert result.status == "not_capable"
    assert result.agent is not None
    assert result.agent.id == "cli:codex"


def test_pick_default_chair_skips_incapable_cli_then_mock() -> None:
    agents = [
        AgentInfo(
            id="cli:claude",
            kind="cli",
            label="Claude Code CLI",
            available=True,
            runnable=False,
            aliases=["claude"],
            chair_capable=False,
            chair_unavailable_reason="尚無 chair adapter（P1）",
        ),
        AgentInfo(
            id="mock",
            kind="mock",
            label="Mock",
            available=True,
            runnable=True,
            model="mock",
            aliases=["mock"],
            chair_capable=True,
        ),
    ]
    result = pick_default_chair_agent(agents)
    assert result.status == "unique"
    assert result.agent is not None
    assert result.agent.id == "mock"


def test_pick_default_prefers_qwen_over_mock() -> None:
    agents = [
        _qwen("qwen3_8b", "qwen3:8b"),
        AgentInfo(
            id="mock",
            kind="mock",
            label="Mock",
            available=True,
            runnable=True,
            model="mock",
            aliases=["mock"],
            chair_capable=True,
        ),
    ]
    result = pick_default_chair_agent(agents)
    assert result.agent is not None
    assert result.agent.id == "ollama:qwen3_8b"


def test_preferred_chair_failure_is_not_silent() -> None:
    agents = [
        AgentInfo(
            id="mock",
            kind="mock",
            label="Mock",
            available=True,
            runnable=True,
            aliases=["mock"],
            chair_capable=True,
        )
    ]
    result = pick_default_chair_agent(agents, preferred="Codex")
    assert result.status in {"not_found", "not_capable"}
    assert result.agent is None or result.status != "unique"


# ---------------------------------------------------------------------------
# session list / latest
# ---------------------------------------------------------------------------


def _meta(sid: str, created: str) -> dict:
    return {
        "schema": "mk-xinone.session.meta.v1",
        "id": sid,
        "preset": "council-lite",
        "status": "completed",
        "created_at": created,
        "seats": [],
    }


def test_list_and_latest_session(tmp_path: Path) -> None:
    older = tmp_path / "older"
    newer = tmp_path / "newer"
    junk = tmp_path / "no-meta"
    older.mkdir()
    newer.mkdir()
    junk.mkdir()
    write_json(older / "meta.json", _meta("older", "2026-08-01T00:00:00+08:00"))
    write_json(newer / "meta.json", _meta("newer", "2026-08-13T12:00:00+08:00"))
    (junk / "readme.txt").write_text("skip", encoding="utf-8")

    listed = list_sessions(tmp_path)
    assert [p.name for p in listed] == ["newer", "older"]
    latest = latest_session(tmp_path)
    assert latest is not None
    assert latest.name == "newer"


def test_latest_session_empty(tmp_path: Path) -> None:
    assert list_sessions(tmp_path) == []
    assert latest_session(tmp_path) is None


# ---------------------------------------------------------------------------
# CLI §10 (sessions_dir → tmp_path)
# ---------------------------------------------------------------------------


def _stub_discover() -> DiscoveryResult:
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
    codex = AgentInfo(
        id="cli:codex",
        kind="cli",
        label="Codex CLI",
        available=True,
        runnable=False,
        aliases=["codex"],
        chair_capable=False,
        chair_unavailable_reason="尚無 chair adapter（P1）",
    )
    return DiscoveryResult(agents=[mock, codex], runnable=[mock], notes=["test stub"])


def _run_chat(monkeypatch, tmp_path: Path, lines: list[str], extra_args: list[str] | None = None) -> str:
    monkeypatch.setattr("mk_xinone.cli.discover_agents", _stub_discover)
    monkeypatch.setattr("mk_xinone.cli.sessions_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "mk_xinone.cli.warmup_chair",
        lambda *args, **kwargs: (True, "skip"),
    )
    stream = iter([*lines, "/quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(stream))
    try:
        main(["chat", "--backend", "mock", "--no-all-agents", *(extra_args or [])])
    except SystemExit as exc:
        assert exc.code in {0, 1, 3}
    return ""


def _session_dirs(tmp_path: Path) -> list[Path]:
    return [p for p in tmp_path.iterdir() if p.is_dir() and (p / "meta.json").is_file()]


def test_cli_1_hi_no_session(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(monkeypatch, tmp_path, ["嗨，先跟你聊聊。"])
    out = capsys.readouterr().out
    assert _session_dirs(tmp_path) == []
    assert "開會確認" not in out
    assert "主席" in out


def test_cli_2_chat_only_soft_eval_no_card(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(
        monkeypatch,
        tmp_path,
        ["先不要開會，幫我整理三點。", "幫我評估這件事的風險"],
    )
    out = capsys.readouterr().out
    assert _session_dirs(tmp_path) == []
    assert "開會確認" not in out


def test_cli_3_convene_confirm_enter_creates_session(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(
        monkeypatch,
        tmp_path,
        ["召集大家開會，評估本地 session 當 SSOT。", ""],
    )
    out = capsys.readouterr().out
    assert "開會確認" in out
    created = _session_dirs(tmp_path)
    assert len(created) == 1
    meta = (created[0] / "meta.json").read_text(encoding="utf-8")
    assert "chair" in meta
    assert "completed" in out or "MOCK" in out


def test_cli_4_multi_agent_compare_shows_card(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(monkeypatch, tmp_path, ["請多個 agent 比較方案 A 和 B。", "n"])
    out = capsys.readouterr().out
    assert "開會確認" in out
    assert _session_dirs(tmp_path) == []


def test_cli_5_open_meeting_asks_goal(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(monkeypatch, tmp_path, ["開個會。"])
    out = capsys.readouterr().out
    assert "開會確認" not in out
    assert _session_dirs(tmp_path) == []
    assert "什麼" in out or "?" in out or "？" in out


def test_cli_appoint_capable_codex(monkeypatch, capsys, tmp_path: Path) -> None:
    def stub() -> DiscoveryResult:
        mock = AgentInfo(
            id="mock",
            kind="mock",
            label="Mock",
            available=True,
            runnable=True,
            aliases=["mock"],
            chair_capable=True,
        )
        codex = AgentInfo(
            id="cli:codex",
            kind="cli",
            label="Codex CLI",
            available=True,
            runnable=False,
            aliases=["codex"],
            chair_capable=True,
        )
        return DiscoveryResult(agents=[mock, codex], runnable=[mock], notes=[])

    monkeypatch.setattr("mk_xinone.cli.discover_agents", stub)
    monkeypatch.setattr("mk_xinone.cli.sessions_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "mk_xinone.cli.warmup_chair",
        lambda *args, **kwargs: (True, "skip"),
    )
    stream = iter(["讓 Codex 當主席。", "/quit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(stream))
    try:
        main(["chat", "--backend", "mock", "--no-all-agents"])
    except SystemExit as exc:
        assert exc.code in {0, 1, 3}
    out = capsys.readouterr().out
    assert "已由 Codex 主持" in out
    assert "尚未開會" in out
    assert _session_dirs(tmp_path) == []


def test_cli_6_appoint_codex_not_capable_keeps_mock(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(monkeypatch, tmp_path, ["讓 Codex 當主席。"])
    out = capsys.readouterr().out
    assert _session_dirs(tmp_path) == []
    assert "開會確認" not in out
    assert "不能" in out or "無法" in out or "尚無" in out
    assert "Mock" in out


def test_cli_7_you_chair_then_card(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(
        monkeypatch,
        tmp_path,
        ["你來當主席，召集大家評估這份提案。", "n"],
    )
    out = capsys.readouterr().out
    assert "開會確認" in out
    assert "提案" in out
    assert _session_dirs(tmp_path) == []


def test_cli_8_revoke_no_session(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(monkeypatch, tmp_path, ["不要讓 Codex 當主席了，恢復預設。"])
    out = capsys.readouterr().out
    assert _session_dirs(tmp_path) == []
    assert "預設" in out or "Mock" in out


def test_cli_9_list_agents_no_session(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(monkeypatch, tmp_path, ["現在有哪些 agent？誰能當主席？"])
    out = capsys.readouterr().out
    assert _session_dirs(tmp_path) == []
    assert "chair" in out.lower() or "主席" in out
    assert "Mock" in out


def test_cli_10_show_last_no_new_session(monkeypatch, capsys, tmp_path: Path) -> None:
    existing = tmp_path / "2026-08-13-prior"
    existing.mkdir()
    write_json(existing / "meta.json", _meta("2026-08-13-prior", "2026-08-13T10:00:00+08:00"))
    before = _session_dirs(tmp_path)
    _run_chat(monkeypatch, tmp_path, ["顯示上一場會議結果。"])
    out = capsys.readouterr().out
    after = _session_dirs(tmp_path)
    assert len(after) == len(before)
    assert "2026-08-13-prior" in out
    assert "開會確認" not in out


def test_cli_startup_prints_chair(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(monkeypatch, tmp_path, [])
    out = capsys.readouterr().out
    assert "主席：" in out
    assert "/council" not in out.split("人話")[0] if "人話" in out else "/council" not in out


def test_cli_slash_council_still_asks_confirm(monkeypatch, capsys, tmp_path: Path) -> None:
    _run_chat(
        monkeypatch,
        tmp_path,
        ["/council 評估本地 session 當 SSOT 是否合理", ""],
    )
    out = capsys.readouterr().out
    assert "開會確認" in out
    assert _session_dirs(tmp_path)


def test_no_subcommand_defaults_to_chat() -> None:
    assert _default_to_chat([]) == ["chat"]
    assert _default_to_chat(["--backend", "mock"]) == ["chat", "--backend", "mock"]
    assert _default_to_chat(["run", "hello"]) == ["run", "hello"]
    assert _default_to_chat(["--help"]) == ["--help"]


def test_assignment_roundtrip() -> None:
    a = ChairAssignment(
        agent_id="mock",
        label="Mock",
        source="default",
        appointed_at_turn=0,
    )
    state = ChatState(default_chair=a, active_chair=a)
    assert state.active_chair is not None
    assert state.active_chair.label == "Mock"
    assert state.convene_mode == "normal"
    assert state.pending_confirm is None
