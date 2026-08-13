"""Discover runnable agents and build all-hands seat lists."""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

from mk_xinone.backends.openai_compatible import resolve_openai_settings

# Models that cannot chat as council seats
_SKIP_MODEL = re.compile(
    r"(embed|bge-|e5-|rerank|whisper|tts|clip|llava|vision)",
    re.IGNORECASE,
)

# Role rotation for discovered agents (workers only; synthesizer separate)
_ROLE_CYCLE: list[tuple[str, str, str]] = [
    ("architect", "Architect", "目標是否對、邊界、風險、是否該做"),
    ("analyst", "Analyst", "結構、一致性、可驗證事實、缺口"),
    ("engineer", "Engineer", "可不可做、怎麼驗、實作風險"),
    ("risk", "Risk", "尾部風險、失敗模式、可逆性"),
    ("product", "Product", "使用者價值、注意力成本、上線順序"),
    ("security", "Security", "資安、機密、權限與濫用面"),
    ("ops", "Ops", "部署、觀測、回滾、運維負擔"),
    ("devil", "DevilAdvocate", "刻意反對主流結論、找盲點"),
]


@dataclass
class AgentInfo:
    id: str
    kind: str  # ollama | openai | mock | cli
    label: str
    available: bool
    model: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    runnable: bool = True  # can seat-run today
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiscoveryResult:
    agents: list[AgentInfo] = field(default_factory=list)
    runnable: list[AgentInfo] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary_line(self) -> str:
        n = len(self.runnable)
        kinds = {}
        for a in self.runnable:
            kinds[a.kind] = kinds.get(a.kind, 0) + 1
        parts = ", ".join(f"{k}×{v}" for k, v in sorted(kinds.items()))
        return f"{n} runnable agent(s)" + (f" ({parts})" if parts else "")


def _http_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 1.5) -> Any:
    """GET JSON with a hard wall-clock timeout (thread join)."""
    from concurrent.futures import ThreadPoolExecutor
    from concurrent.futures import TimeoutError as FuturesTimeout

    def _do() -> Any:
        req = urllib.request.Request(
            url,
            headers=headers or {"User-Agent": "mk-xinone-agents/0.1"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_do)
        try:
            return fut.result(timeout=timeout + 0.5)
        except FuturesTimeout as e:
            raise TimeoutError(f"timeout fetching {url}") from e


def _discover_ollama(host: str | None = None) -> list[AgentInfo]:
    base = (host or os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434").rstrip("/")
    out: list[AgentInfo] = []
    try:
        data = _http_json(f"{base}/api/tags")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError):
        return [
            AgentInfo(
                id="ollama",
                kind="ollama",
                label="Ollama",
                available=False,
                runnable=False,
                base_url=base + "/v1",
                detail="not reachable",
            )
        ]
    models = data.get("models") or []
    for m in models:
        name = str(m.get("name") or m.get("model") or "").strip()
        if not name:
            continue
        if _SKIP_MODEL.search(name):
            out.append(
                AgentInfo(
                    id=f"ollama:{name}",
                    kind="ollama",
                    label=f"Ollama/{name}",
                    available=True,
                    model=name,
                    base_url=base + "/v1",
                    runnable=False,
                    detail="skipped (embedding/vision)",
                )
            )
            continue
        safe_id = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
        out.append(
            AgentInfo(
                id=f"ollama:{safe_id}",
                kind="ollama",
                label=f"Ollama/{name}",
                available=True,
                model=name,
                base_url=base + "/v1",
                api_key_env=None,
                runnable=True,
                detail="chat model",
            )
        )
    if not any(a.runnable for a in out):
        out.append(
            AgentInfo(
                id="ollama:none",
                kind="ollama",
                label="Ollama (no chat models)",
                available=True,
                runnable=False,
                base_url=base + "/v1",
                detail="reachable but no chat models",
            )
        )
    return out


def _discover_openai() -> list[AgentInfo]:
    cfg = resolve_openai_settings()
    key = cfg["api_key"]
    base = cfg["base_url"]
    model = cfg["model"]
    # Skip if this is clearly local ollama already listed
    if "11434" in base:
        return []
    if not key and "api.openai.com" in base:
        return [
            AgentInfo(
                id="openai:cloud",
                kind="openai",
                label="OpenAI-compatible (no key)",
                available=False,
                model=model,
                base_url=base,
                api_key_env="OPENAI_API_KEY",
                runnable=False,
                detail="set XINONE_API_KEY or OPENAI_API_KEY",
            )
        ]
    # Key present or non-cloud endpoint
    if key or "localhost" in base or "127.0.0.1" in base:
        return [
            AgentInfo(
                id="openai:default",
                kind="openai",
                label=f"OpenAI-compatible/{model}",
                available=True,
                model=model,
                base_url=base,
                api_key_env="OPENAI_API_KEY" if key else None,
                runnable=True,
                detail="env model",
            )
        ]
    return [
        AgentInfo(
            id="openai:default",
            kind="openai",
            label=f"OpenAI-compatible/{model}",
            available=False,
            model=model,
            base_url=base,
            runnable=False,
            detail="no API key",
        )
    ]


def _discover_cli() -> list[AgentInfo]:
    """Detect CLI agents on PATH (informational; not all runnable in-process yet)."""
    tools = [
        ("claude", "Claude Code CLI"),
        ("codex", "Codex CLI"),
        ("gemini", "Gemini CLI"),
        ("agentx", "agentX"),
    ]
    out: list[AgentInfo] = []
    for cmd, label in tools:
        path = shutil.which(cmd)
        out.append(
            AgentInfo(
                id=f"cli:{cmd}",
                kind="cli",
                label=label,
                available=bool(path),
                runnable=False,  # no in-process seat runner yet
                detail=path or "not on PATH",
            )
        )
    return out


def discover_agents(
    *,
    include_mock: bool = True,
    include_cli: bool = True,
    ollama_host: str | None = None,
) -> DiscoveryResult:
    agents: list[AgentInfo] = []
    notes: list[str] = []

    ollama = _discover_ollama(ollama_host)
    agents.extend(ollama)
    if any(a.runnable and a.kind == "ollama" for a in ollama):
        notes.append("ollama chat models detected")
    elif any(a.kind == "ollama" and not a.available for a in ollama):
        notes.append("ollama not reachable")

    agents.extend(_discover_openai())

    if include_cli:
        agents.extend(_discover_cli())
        cli_up = [a for a in agents if a.kind == "cli" and a.available]
        if cli_up:
            notes.append(
                f"CLI present but not in-process seats yet: "
                f"{', '.join(a.label for a in cli_up)}"
            )

    runnable = [a for a in agents if a.runnable]
    if not runnable and include_mock:
        agents.append(
            AgentInfo(
                id="mock",
                kind="mock",
                label="Mock",
                available=True,
                model="mock",
                runnable=True,
                detail="fallback when no real agents",
            )
        )
        notes.append("no real agents — mock fallback")
        runnable = [a for a in agents if a.runnable]
    elif include_mock and not any(a.kind == "mock" for a in agents):
        # mock always listed as available optional, but not auto-joined if reals exist
        agents.append(
            AgentInfo(
                id="mock",
                kind="mock",
                label="Mock",
                available=True,
                model="mock",
                runnable=True,
                detail="available; excluded from all-hands when reals exist",
            )
        )

    # Prefer real agents for "all hands"
    real = [a for a in runnable if a.kind != "mock"]
    use = real if real else runnable

    return DiscoveryResult(agents=agents, runnable=use, notes=notes)


def build_all_hands_preset(
    discovery: DiscoveryResult | None = None,
    *,
    max_workers: int = 12,
    include_synthesizer: bool = True,
    preset_id: str = "all-hands",
) -> dict[str, Any]:
    """
    Build a dynamic preset: every runnable agent becomes a worker seat.
    Roles rotate through Architect/Analyst/… ; last synthesizer uses first agent.
    """
    disc = discovery or discover_agents()
    workers_src = list(disc.runnable)
    # If mock is in runnable alongside reals, drop mock (discover already prefers reals)
    if any(a.kind != "mock" for a in workers_src):
        workers_src = [a for a in workers_src if a.kind != "mock"]

    if not workers_src:
        workers_src = [
            AgentInfo(
                id="mock",
                kind="mock",
                label="Mock",
                available=True,
                runnable=True,
                model="mock",
            )
        ]

    workers_src = workers_src[:max_workers]
    seats: list[dict[str, Any]] = []
    for i, agent in enumerate(workers_src):
        role_id, role_name, mission = _ROLE_CYCLE[i % len(_ROLE_CYCLE)]
        # unique seat id when multiple agents map to same role name
        seat_id = f"{role_id}_{i}" if i >= len(_ROLE_CYCLE) else role_id
        if any(s["id"] == seat_id for s in seats):
            seat_id = f"{role_id}_{i}"
        seat: dict[str, Any] = {
            "id": seat_id,
            "role": role_name if i < len(_ROLE_CYCLE) else f"{role_name}-{i + 1}",
            "mission": mission,
            "agent_id": agent.id,
            "agent_label": agent.label,
            "backend": agent.kind if agent.kind != "cli" else "mock",
            "model": agent.model,
            "base_url": agent.base_url,
        }
        if agent.kind == "ollama":
            seat["backend"] = "openai"  # OpenAI-compatible endpoint
            seat["api_key"] = "ollama"
        elif agent.kind == "openai":
            seat["backend"] = "openai"
        elif agent.kind == "mock":
            seat["backend"] = "mock"
        seats.append(seat)

    if include_synthesizer and workers_src:
        lead = workers_src[0]
        seats.append(
            {
                "id": "synthesizer",
                "role": "Synthesizer",
                "mission": "綜合各席結構化產出；標共識／分歧／判決；不得發明未出現的事實",
                "kind": "synthesizer",
                "agent_id": lead.id,
                "agent_label": lead.label,
                "backend": "openai" if lead.kind in {"ollama", "openai"} else "mock",
                "model": lead.model,
                "base_url": lead.base_url,
                "api_key": "ollama" if lead.kind == "ollama" else None,
            }
        )

    return {
        "id": preset_id,
        "name": "All Hands",
        "description": f"Dynamic: {len(workers_src)} agent(s) + synthesizer",
        "seats": seats,
        "synthesis": True,
        "harness": {
            "wall_max_retries": 2,
            "require_verdict": True,
            "no_self_accept": False,
        },
        "all_hands": True,
        "discovered": [a.to_dict() for a in workers_src],
    }


def format_agents_table(discovery: DiscoveryResult) -> str:
    lines = [
        f"discovered: {len(discovery.agents)}  runnable(all-hands): {len(discovery.runnable)}",
        discovery.summary_line(),
        "",
        f"{'status':8} {'kind':8} {'run':5} label",
        "-" * 56,
    ]
    for a in discovery.agents:
        st = "UP" if a.available else "DOWN"
        run = "yes" if a.runnable and a in discovery.runnable else (
            "yes*" if a.runnable else "no"
        )
        # runnable but excluded (mock when reals exist)
        if a.runnable and a not in discovery.runnable:
            run = "skip"
        lines.append(f"{st:8} {a.kind:8} {run:5} {a.label}")
        if a.detail:
            lines.append(f"{'':8} {'':8} {'':5}  → {a.detail}")
    if discovery.notes:
        lines.append("")
        lines.append("notes:")
        for n in discovery.notes:
            lines.append(f"  - {n}")
    lines.append("")
    lines.append("all-hands: every runnable agent joins as a seat (+ synthesizer)")
    return "\n".join(lines) + "\n"
