"""Discover runnable agents and build all-hands seat lists."""

from __future__ import annotations

import json
import os
import re
import shutil
import urllib.error
import urllib.request
from collections.abc import Sequence
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


# Startup default-chair pool (D2). First chair_capable wins.
DEFAULT_CHAIR_ORDER: tuple[str, ...] = (
    "claude",
    "codex",
    "gemini",
    "grok",
    "qwen",
    "gemma",
    "agy",
    "mock",
)

_CLI_TOOLS: list[tuple[str, str, list[str]]] = [
    ("claude", "Claude Code CLI", ["claude", "claude code", "claude-code"]),
    ("codex", "Codex CLI", ["codex"]),
    ("gemini", "Gemini CLI", ["gemini"]),
    ("grok", "Grok", ["grok"]),
    ("agentx", "agentX", ["agy", "agentx", "agent x"]),
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
    aliases: list[str] = field(default_factory=list)
    chair_capable: bool = False
    chair_unavailable_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResolveResult:
    status: str  # unique | ambiguous | not_capable | not_found
    agent: AgentInfo | None = None
    candidates: list[AgentInfo] = field(default_factory=list)
    message: str = ""


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
                    aliases=_ollama_aliases(name),
                    chair_capable=False,
                    chair_unavailable_reason="skipped (embedding/vision)",
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
                aliases=_ollama_aliases(name),
                chair_capable=True,
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
                chair_capable=False,
                chair_unavailable_reason="no API key",
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
                aliases=_ollama_aliases(model) if model else [],
                chair_capable=True,
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
            chair_capable=False,
            chair_unavailable_reason="no API key",
        )
    ]


def _discover_cli() -> list[AgentInfo]:
    """Detect CLI agents. Chair-capable if on PATH and a print/exec recipe exists."""
    from mk_xinone.backends.cli_chair import has_cli_chair_recipe, probe_cli_chair_ready

    out: list[AgentInfo] = []
    for cmd, label, aliases in _CLI_TOOLS:
        path = shutil.which(cmd)
        ready, ready_reason = (False, "not on PATH")
        if path and has_cli_chair_recipe(cmd):
            ready, ready_reason = probe_cli_chair_ready(cmd)
        elif path:
            ready, ready_reason = False, "尚無 chair adapter（P1）"
        can_chair = bool(path) and ready
        reason = ""
        if not path:
            reason = "not on PATH"
        elif not can_chair:
            reason = ready_reason or "尚無 chair adapter（P1）"
        else:
            reason = "chair via CLI print/exec；尚未能入席"
        out.append(
            AgentInfo(
                id=f"cli:{cmd}",
                kind="cli",
                label=label,
                available=bool(path),
                runnable=False,  # no in-process seat runner yet
                detail=path or "not on PATH",
                aliases=list(aliases),
                chair_capable=can_chair,
                chair_unavailable_reason="" if can_chair else reason,
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
            chairs = [a.label for a in cli_up if a.chair_capable]
            if chairs:
                notes.append(f"CLI chair-capable: {', '.join(chairs)}")
            notes.append(
                "CLI 尚不能入席（seat=no）："
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
                aliases=["mock"],
                chair_capable=True,
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
                aliases=["mock"],
                chair_capable=True,
            )
        )

    # Prefer real agents for "all hands"
    real = [a for a in runnable if a.kind != "mock"]
    use = real if real else runnable

    return DiscoveryResult(agents=agents, runnable=use, notes=notes)


_IDENTITY_KEYS: tuple[str, ...] = (
    "claude",
    "codex",
    "gemini",
    "grok",
    "qwen",
    "gemma",
    "agy",
    "mock",
)
_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*b\b", re.IGNORECASE)


def agent_identity(agent: AgentInfo) -> str:
    """Stable identity bucket (one seat per identity in all-hands)."""
    tokens = _agent_tokens(agent)
    if agent.id == "cli:agentx" or bool(tokens & {"agy", "agentx", "agent x"}):
        return "agy"
    for key in _IDENTITY_KEYS:
        if key == "agy":
            continue
        if key in tokens or agent.id == f"cli:{key}":
            return key
    if agent.model:
        return agent.model.split(":")[0].lower()
    if ":" in agent.id:
        return agent.id.split(":", 1)[1].split("_")[0].lower()
    return agent.id


def _size_hint(agent: AgentInfo) -> float:
    blob = f"{agent.model or ''} {agent.id}"
    match = _SIZE_RE.search(blob)
    if match:
        return float(match.group(1))
    return 50.0


def select_identity_roster(
    agents: Sequence[AgentInfo],
    *,
    max_workers: int = 4,
) -> list[AgentInfo]:
    """At most one runnable seat per identity; prefer smaller local models."""
    real = [a for a in agents if a.runnable and a.kind != "mock"]
    src = real or [a for a in agents if a.runnable]
    by_id: dict[str, AgentInfo] = {}
    for agent in src:
        key = agent_identity(agent)
        prev = by_id.get(key)
        if prev is None or _size_hint(agent) < _size_hint(prev):
            by_id[key] = agent
    ordered: list[AgentInfo] = []
    seen: set[str] = set()
    for key in _IDENTITY_KEYS:
        if key in by_id:
            ordered.append(by_id[key])
            seen.add(key)
    for key, agent in by_id.items():
        if key not in seen:
            ordered.append(agent)
    return ordered[:max_workers]


def build_all_hands_preset(
    discovery: DiscoveryResult | None = None,
    *,
    max_workers: int = 4,
    include_synthesizer: bool = True,
    preset_id: str = "all-hands",
    avoid_agent_id: str | None = None,
) -> dict[str, Any]:
    """
    Identity-first roster: one seat per identity (no 4× Ollama flood).
    Roles rotate through Architect/Analyst/… ; synthesizer prefers a non-chair actor.
    """
    disc = discovery or discover_agents()
    workers_src = select_identity_roster(disc.runnable, max_workers=max_workers)

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
        lead = next(
            (w for w in workers_src if avoid_agent_id and w.id != avoid_agent_id),
            workers_src[0],
        )
        if avoid_agent_id and lead.id == avoid_agent_id and len(workers_src) > 1:
            lead = workers_src[1]
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


def _norm_ref(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _ollama_aliases(model: str) -> list[str]:
    name = (model or "").strip()
    if not name:
        return []
    stem = name.split(":")[0]
    aliases = [name, stem, name.replace(":", "_"), stem.lower()]
    low = stem.lower()
    if low.startswith("qwen"):
        aliases.append("qwen")
    if low.startswith("gemma"):
        aliases.append("gemma")
    out: list[str] = []
    seen: set[str] = set()
    for item in aliases:
        key = item.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def _agent_tokens(agent: AgentInfo) -> set[str]:
    raw = [agent.id, agent.label, agent.model or "", *agent.aliases]
    if ":" in agent.id:
        raw.append(agent.id.split(":", 1)[1])
    if "/" in agent.label:
        raw.append(agent.label.split("/", 1)[1])
    tokens: set[str] = set()
    for item in raw:
        n = _norm_ref(item)
        if not n:
            continue
        tokens.add(n)
        tokens.add(n.replace(":", "_"))
        tokens.add(n.replace("_", ":"))
        tokens.add(n.split(":")[0])
        tokens.add(n.split("/")[-1])
    return {t for t in tokens if t}


def resolve_agent_ref(
    ref: str,
    agents: Sequence[AgentInfo],
    *,
    for_chair: bool = False,
) -> ResolveResult:
    """Resolve a user agent string. Never pick the first of several hits."""
    key = _norm_ref(ref)
    if not key:
        return ResolveResult(status="not_found", message="empty ref")

    hits = [a for a in agents if key in _agent_tokens(a)]
    if not hits:
        return ResolveResult(status="not_found", message=f"not found: {ref}")
    if len(hits) > 1:
        return ResolveResult(
            status="ambiguous",
            candidates=hits,
            message=f"ambiguous: {ref}",
        )
    agent = hits[0]
    if for_chair and not agent.chair_capable:
        return ResolveResult(
            status="not_capable",
            agent=agent,
            candidates=[agent],
            message=agent.chair_unavailable_reason or "not chair_capable",
        )
    return ResolveResult(status="unique", agent=agent, candidates=[agent], message="ok")


def _pool_match(pool: str, agent: AgentInfo) -> bool:
    tokens = _agent_tokens(agent)
    if pool == "agy":
        return bool(tokens & {"agy", "agentx", "agent x"}) or agent.id == "cli:agentx"
    if pool == "mock":
        return agent.kind == "mock" or agent.id == "mock"
    return pool in tokens or agent.id == f"cli:{pool}"


def pick_default_chair_agent(
    agents: Sequence[AgentInfo],
    *,
    preferred: str | None = None,
) -> ResolveResult:
    """
    First chair_capable agent in DEFAULT_CHAIR_ORDER.

    If preferred is set and fails, return that failure (D5: no silent swap).
    """
    if preferred:
        return resolve_agent_ref(preferred, agents, for_chair=True)

    for pool in DEFAULT_CHAIR_ORDER:
        capable = [a for a in agents if _pool_match(pool, a) and a.chair_capable]
        if capable:
            return ResolveResult(
                status="unique",
                agent=capable[0],
                candidates=capable,
                message=f"default:{pool}",
            )
    return ResolveResult(status="not_found", message="no chair_capable agent")


def format_agents_table(discovery: DiscoveryResult) -> str:
    lines = [
        f"discovered: {len(discovery.agents)}  runnable(all-hands): {len(discovery.runnable)}",
        discovery.summary_line(),
        "",
        f"{'status':8} {'kind':8} {'chair':5} {'seat':5} label",
        "-" * 64,
    ]
    for a in discovery.agents:
        st = "UP" if a.available else "DOWN"
        chair = "yes" if a.chair_capable else "no"
        if a.runnable and a in discovery.runnable:
            seat = "yes"
        elif a.runnable:
            seat = "skip"
        else:
            seat = "no"
        lines.append(f"{st:8} {a.kind:8} {chair:5} {seat:5} {a.label}")
        extra = a.chair_unavailable_reason or a.detail
        if extra:
            lines.append(f"{'':8} {'':8} {'':5} {'':5}  → {extra}")
    if discovery.notes:
        lines.append("")
        lines.append("notes:")
        for n in discovery.notes:
            lines.append(f"  - {n}")
    lines.append("")
    lines.append("columns: detected=status  chair=chair_capable  seat=runnable")
    lines.append("all-hands: one seat per identity (+ synthesizer); CLI chair ≠ seat")
    return "\n".join(lines) + "\n"
