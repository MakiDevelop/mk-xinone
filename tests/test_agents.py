from __future__ import annotations

from mk_xinone.agents import (
    AgentInfo,
    DiscoveryResult,
    build_all_hands_preset,
    discover_agents,
    format_agents_table,
)


def test_discover_agents_returns_runnable(monkeypatch):
    # Avoid hanging on slow Ollama/network in CI/dev
    monkeypatch.setattr(
        "mk_xinone.agents._discover_ollama",
        lambda host=None: [
            AgentInfo(
                id="ollama:q",
                kind="ollama",
                label="Ollama/q",
                available=True,
                model="q:latest",
                base_url="http://127.0.0.1:11434/v1",
                runnable=True,
            )
        ],
    )
    monkeypatch.setattr("mk_xinone.agents._discover_openai", list)
    monkeypatch.setattr("mk_xinone.agents._discover_cli", list)
    disc = discover_agents(include_cli=False)
    assert isinstance(disc, DiscoveryResult)
    assert disc.runnable
    assert all(a.runnable for a in disc.runnable)


def test_build_all_hands_from_fake_agents():
    agents = [
        AgentInfo(
            id="ollama:a",
            kind="ollama",
            label="Ollama/a",
            available=True,
            model="a:latest",
            base_url="http://127.0.0.1:11434/v1",
            runnable=True,
        ),
        AgentInfo(
            id="ollama:b",
            kind="ollama",
            label="Ollama/b",
            available=True,
            model="b:latest",
            base_url="http://127.0.0.1:11434/v1",
            runnable=True,
        ),
    ]
    disc = DiscoveryResult(agents=agents, runnable=agents)
    preset = build_all_hands_preset(disc)
    assert preset["all_hands"] is True
    # 2 workers + synthesizer
    assert len(preset["seats"]) == 3
    workers = [s for s in preset["seats"] if s.get("kind") != "synthesizer"]
    assert len(workers) == 2
    assert workers[0]["model"] == "a:latest"
    assert workers[1]["model"] == "b:latest"
    assert any(s["id"] == "synthesizer" for s in preset["seats"])


def test_format_agents_table():
    agents = [
        AgentInfo(
            id="mock",
            kind="mock",
            label="Mock",
            available=True,
            runnable=True,
        )
    ]
    disc = DiscoveryResult(agents=agents, runnable=agents, notes=["n"])
    text = format_agents_table(disc)
    assert "runnable" in text
    assert "all-hands" in text
