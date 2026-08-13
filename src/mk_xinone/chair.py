"""Chair-first dialogue: NL intent first; other seats stay silent unless convened."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from mk_xinone.agents import AgentInfo, ResolveResult, resolve_agent_ref
from mk_xinone.backends import get_runner
from mk_xinone.backends.cli_chair import (
    bind_cli_workspace,
    build_chair_prompt,
    cli_cmd_from_agent_id,
    run_cli_chair,
)
from mk_xinone.backends.openai_compatible import (
    OpenAICompatibleSeatRunner,
    _extract_json_object,
)

_GREETING = re.compile(
    r"^(哈囉|嗨|你好|您好|hello|hi|hey|早安|午安|晚安|在嗎|嗨嗨)[\s\W]*$",
    re.IGNORECASE,
)

# Explicit multi-seat only. 評估／分析／風險 alone must NOT convene (D4).
_COLLECTIVE_RE = re.compile(
    r"(召集大家(?:開會)?|召集各席|請大家(?:審議|開會|評估|比較)|"
    r"開(?:個|一場|一次)?會|請多個\s*agents?|多個\s*agents?|"
    r"多席|(?:開|跑|來一場)\s*council|\bcouncil\b|全員(?:開會|加入)?)",
    re.IGNORECASE,
)

_APPOINT_NAMED = re.compile(
    r"(?:讓|請|改由|指定)\s*(?P<ref>.+?)\s*(?:來)?(?:當|做|擔任)\s*主席|"
    r"主席\s*(?:換成|改成|改為)\s*(?P<ref2>.+?)(?=[，,。！!？?\s]|$)",
    re.IGNORECASE,
)
_APPOINT_YOU = re.compile(r"你來當主席|你當主席|你來主持|你主持", re.IGNORECASE)

_REVOKE = re.compile(
    r"恢復預設(?:主席)?|取消主席(?:指派)?|不要讓.+?當主席了|撤銷主席",
    re.IGNORECASE,
)

_CHAT_ONLY = re.compile(
    r"先不要開會|先別開會|不要開會|只跟你聊|不用找其他人|只跟主席聊",
    re.IGNORECASE,
)

_LIST = re.compile(
    r"有哪些\s*agents?|誰能當主席|目前有哪些(?:席次|agents?)|"
    r"列出.*agents?|現在有哪些\s*agents?",
    re.IGNORECASE,
)

_LAST = re.compile(
    r"上一場會議|最近(?:一次|一場)?(?:會議|session)|顯示.*會議|"
    r"剛剛.*session|會議結果",
    re.IGNORECASE,
)

_EXIT = re.compile(r"^(?:/)?(?:quit|exit|q)$", re.IGNORECASE)

_CONFIRM_YES = re.compile(r"^(y|yes|是|開|開會|確認)$", re.IGNORECASE)
_CONFIRM_NO = re.compile(r"^(n|no|取消|不要|不開)$", re.IGNORECASE)


@dataclass
class IntentPlan:
    primary: str  # reply | convene | list_agents | show_last_session | clarify | exit
    chair_change: str = "keep"  # keep | appoint | revoke
    chair_ref: str | None = None
    goal: str | None = None
    question: str | None = None
    reason: str = ""
    stay_chat_only: bool = False
    explicit_multi_seat: bool = False


@dataclass
class ChairAssignment:
    agent_id: str
    label: str
    source: str  # default | user-explicit
    appointed_at_turn: int = 0

    def to_meta(self) -> dict[str, str | int]:
        return {
            "agent_id": self.agent_id,
            "label": self.label,
            "source": self.source,
            "appointed_at_turn": self.appointed_at_turn,
        }


@dataclass
class ConveneCard:
    goal: str
    chair: ChairAssignment
    seat_count: int
    roster_label: str


@dataclass
class ChairDecision:
    action: str  # "reply" | "convene"
    message: str
    goal: str | None = None
    reason: str = ""


@dataclass
class ChatTurn:
    role: str  # user | chair | system
    content: str


@dataclass
class ChatState:
    history: list[ChatTurn] = field(default_factory=list)
    turns: int = 0
    default_chair: ChairAssignment | None = None
    active_chair: ChairAssignment | None = None
    convene_mode: str = "normal"  # normal | chat_only
    pending_confirm: ConveneCard | None = None
    last_session_id: str | None = None
    cli_work_dir: str | None = None
    cli_session_cmd: str | None = None
    cli_session_id: str | None = None
    chair_warmed_id: str | None = None


def _strip_control_phrases(text: str) -> str:
    s = _APPOINT_NAMED.sub("", text)
    s = _APPOINT_YOU.sub("", s)
    s = _REVOKE.sub("", s)
    s = _CHAT_ONLY.sub("", s)
    s = _COLLECTIVE_RE.sub("", s)
    s = re.sub(r"[，,。、！!？?\s]+", " ", s).strip(" ，,。、")
    return s


def _extract_goal(text: str) -> str | None:
    leftover = _strip_control_phrases(text)
    if len(leftover) >= 2:
        return leftover
    return None


def _appoint_ref(text: str) -> tuple[str, str | None]:
    """Return (change, ref). ref is None for「你」."""
    if _REVOKE.search(text):
        return "revoke", None
    if _APPOINT_YOU.search(text):
        return "appoint", None
    m = _APPOINT_NAMED.search(text)
    if m:
        ref = (m.group("ref") or m.group("ref2") or "").strip()
        ref = re.sub(r"^(跟|和|與)\s*", "", ref)
        return "appoint", ref or None
    return "keep", None


def parse_intent(text: str) -> IntentPlan:
    """Deterministic control parser. Model may not authorize convene."""
    raw = (text or "").strip()
    if not raw:
        return IntentPlan(primary="reply", reason="empty")
    if _EXIT.match(raw):
        return IntentPlan(primary="exit", reason="exit")

    has_chat_only = bool(_CHAT_ONLY.search(raw))
    # Strip lock phrases first so「先不要開會」does not count as collective.
    collective_src = _CHAT_ONLY.sub("", raw)
    has_collective = bool(_COLLECTIVE_RE.search(collective_src))
    has_list = bool(_LIST.search(raw))
    has_last = bool(_LAST.search(raw))
    chair_change, chair_ref = _appoint_ref(raw)

    if has_chat_only and has_collective:
        return IntentPlan(
            primary="clarify",
            chair_change=chair_change,
            chair_ref=chair_ref,
            question="這次要維持單聊，還是正式開會？",
            reason="contradiction chat_only+convene",
        )

    goal = _extract_goal(raw) if has_collective else None

    if has_collective and not goal:
        return IntentPlan(
            primary="clarify",
            chair_change=chair_change,
            chair_ref=chair_ref,
            question="這場會要解決什麼？",
            reason="convene missing goal",
        )

    if has_chat_only:
        return IntentPlan(
            primary="reply",
            chair_change=chair_change,
            chair_ref=chair_ref,
            stay_chat_only=True,
            reason="stay_chat_only",
        )

    if has_list and not has_collective:
        return IntentPlan(
            primary="list_agents",
            chair_change=chair_change,
            chair_ref=chair_ref,
            reason="list_agents",
        )

    if has_last and not has_collective:
        return IntentPlan(
            primary="show_last_session",
            chair_change=chair_change,
            chair_ref=chair_ref,
            reason="show_last_session",
        )

    if has_collective and goal:
        return IntentPlan(
            primary="convene",
            chair_change=chair_change,
            chair_ref=chair_ref,
            goal=goal,
            explicit_multi_seat=True,
            reason="collective+goal",
        )

    if chair_change != "keep":
        return IntentPlan(
            primary="reply",
            chair_change=chair_change,
            chair_ref=chair_ref,
            reason="chair change only",
        )

    return IntentPlan(primary="reply", reason="default reply")


def parse_confirm_reply(text: str) -> str:
    """confirm | cancel | appoint | chatter"""
    raw = (text or "").strip()
    if raw == "" or _CONFIRM_YES.match(raw):
        return "confirm"
    if _CONFIRM_NO.match(raw):
        return "cancel"
    plan = parse_intent(raw)
    if plan.chair_change == "appoint":
        return "appoint"
    return "chatter"


def format_convene_card(card: ConveneCard) -> str:
    return (
        "==================================================\n"
        " 開會確認\n"
        "--------------------------------------------------\n"
        f" 目標：{card.goal}\n"
        f" 主席：{card.chair.label}\n"
        f" 席次：{card.seat_count}（{card.roster_label}）\n"
        "==================================================\n"
        " Enter / Y  → 召集開會\n"
        " n / 取消   → 只跟主席聊\n"
        " 或輸入：讓 Gemini 當主席\n"
        "==================================================\n"
    )


def chair_label_for(agent: AgentInfo) -> str:
    by_id = {
        "cli:claude": "Claude",
        "cli:codex": "Codex",
        "cli:gemini": "Gemini",
        "cli:grok": "Grok",
        "cli:agentx": "Agy",
        "mock": "Mock",
    }
    if agent.id in by_id:
        return by_id[agent.id]
    model = (agent.model or "").lower()
    if model.startswith("qwen") or "qwen" in [a.lower() for a in agent.aliases]:
        return "Qwen"
    if model.startswith("gemma") or "gemma" in [a.lower() for a in agent.aliases]:
        return "Gemma"
    return agent.label.split("/")[0] if "/" in agent.label else agent.label


def assignment_from_agent(
    agent: AgentInfo,
    *,
    source: str,
    turn: int = 0,
) -> ChairAssignment:
    return ChairAssignment(
        agent_id=agent.id,
        label=chair_label_for(agent),
        source=source,
        appointed_at_turn=turn,
    )


def apply_chair_change(
    state: ChatState,
    plan: IntentPlan,
    agents: list[AgentInfo],
) -> tuple[bool, str]:
    """Apply appoint/revoke. Failure keeps the current chair (D5)."""
    if plan.chair_change == "keep":
        return True, ""
    before_id = state.active_chair.agent_id if state.active_chair else None
    current = state.active_chair
    current_label = current.label if current else "（無）"

    if plan.chair_change == "revoke":
        if state.default_chair is None:
            return False, f"沒有預設主席可恢復。仍由 {current_label} 主持。"
        state.active_chair = ChairAssignment(
            agent_id=state.default_chair.agent_id,
            label=state.default_chair.label,
            source="default",
            appointed_at_turn=state.turns,
        )
        if state.active_chair.agent_id != before_id:
            _reset_cli_session(state)
        return True, f"已恢復預設主席：{state.active_chair.label}。尚未開會。"

    # appoint
    if plan.chair_ref is None:
        # 「你來當主席」→ current responder
        if current is None:
            return False, "目前沒有回話者可以當主席。"
        matched = next((a for a in agents if a.id == current.agent_id), None)
        if matched is not None and not matched.chair_capable:
            reason = matched.chair_unavailable_reason or "不能主持"
            return False, f"{current.label} 目前不能當主席：{reason}。仍由 {current_label} 主持。"
        state.active_chair = ChairAssignment(
            agent_id=current.agent_id,
            label=current.label,
            source="user-explicit",
            appointed_at_turn=state.turns,
        )
        return True, f"已由 {state.active_chair.label} 主持。尚未開會。"

    result: ResolveResult = resolve_agent_ref(plan.chair_ref, agents, for_chair=True)
    if result.status == "unique" and result.agent is not None:
        state.active_chair = assignment_from_agent(
            result.agent, source="user-explicit", turn=state.turns
        )
        if state.active_chair.agent_id != before_id:
            _reset_cli_session(state)
        return True, f"已由 {state.active_chair.label} 主持。尚未開會。"
    if result.status == "ambiguous":
        names = "、".join(a.label for a in result.candidates)
        return False, (
            f"「{plan.chair_ref}」對應到多個 agent（{names}），"
            f"請指定完整名稱。仍由 {current_label} 主持。"
        )
    if result.status == "not_capable" and result.agent is not None:
        reason = result.agent.chair_unavailable_reason or "尚無 chair adapter"
        return False, (
            f"{chair_label_for(result.agent)} 目前不能當主席：{reason}。"
            f"仍由 {current_label} 主持。"
        )
    return False, f"找不到「{plan.chair_ref}」。仍由 {current_label} 主持。"


def _reset_cli_session(state: ChatState) -> None:
    state.cli_session_cmd = None
    state.cli_session_id = None
    state.chair_warmed_id = None


_WARMUP_PROMPT = (
    "你是 mk-xinone 的主席。之後只回白話，不要自己開會。"
    "記憶只走 AMH，不要用 Google Drive / Gmail。"
    "現在只回：OK"
)


def warmup_chair(
    agent: AgentInfo | None,
    state: ChatState,
    *,
    cli_runner=None,
) -> tuple[bool, str]:
    """Open a persistent chair session as soon as the agent is named."""
    if agent is None or agent.kind == "mock" or not agent.chair_capable:
        return True, "skip"
    if state.chair_warmed_id == agent.id:
        return True, "hot"

    if agent.kind == "cli":
        cmd = cli_cmd_from_agent_id(agent.id)
        if state.cli_session_cmd == cmd and state.cli_session_id:
            state.chair_warmed_id = agent.id
            return True, "hot"
        work_dir, cont, session_id, bound_cmd = bind_cli_workspace(
            state.cli_work_dir,
            cmd,
            state.cli_session_cmd,
            state.cli_session_id,
        )
        timeout = float(os.environ.get("XINONE_CHAIR_TIMEOUT", "90"))
        try:
            run_cli_chair(
                bound_cmd,
                _WARMUP_PROMPT,
                timeout=timeout,
                runner=cli_runner,
                cwd=os.path.join(work_dir, bound_cmd),
                continue_session=cont,
                session_id=session_id,
            )
        except (RuntimeError, OSError, TimeoutError, ValueError) as exc:
            return False, str(exc)
        _remember_cli_session(state, bound_cmd, session_id, work_dir)
        state.chair_warmed_id = agent.id
        return True, "warmed"

    if agent.kind in {"ollama", "openai"}:
        try:
            decide_chair(
                "只回 OK",
                state,
                backend="openai",
                base_url=agent.base_url,
                model=agent.model,
                api_key="ollama" if agent.kind == "ollama" else None,
            )
        except (RuntimeError, OSError, TimeoutError, ValueError) as exc:
            return False, str(exc)
        state.chair_warmed_id = agent.id
        return True, "warmed"

    return True, "skip"


def _remember_cli_session(state: ChatState, cmd: str, session_id: str, work_dir: str) -> None:
    state.cli_work_dir = work_dir
    state.cli_session_cmd = cmd
    state.cli_session_id = session_id


def _history_blob(state: ChatState) -> str:
    return "\n".join(f"{t.role}: {t.content}" for t in state.history[-12:])


def reply_as_chair(
    agent: AgentInfo | None,
    user_text: str,
    state: ChatState,
    *,
    cli_runner=None,
) -> ChairDecision:
    """Reply using the appointed chair's adapter. Fail closed to text, never convene."""
    if agent is None or agent.kind == "mock" or not agent.chair_capable:
        return decide_chair(user_text, state, backend="mock")

    if agent.kind == "cli":
        cmd = cli_cmd_from_agent_id(agent.id)
        work_dir, cont, session_id, bound_cmd = bind_cli_workspace(
            state.cli_work_dir,
            cmd,
            state.cli_session_cmd,
            state.cli_session_id,
        )
        prompt = (
            user_text.strip()
            if cont
            else build_chair_prompt(
                chair_label_for(agent),
                user_text,
                _history_blob(state),
            )
        )
        timeout = float(os.environ.get("XINONE_CHAIR_TIMEOUT", "90"))
        try:
            text = run_cli_chair(
                bound_cmd,
                prompt,
                timeout=timeout,
                runner=cli_runner,
                cwd=os.path.join(work_dir, bound_cmd),
                continue_session=cont,
                session_id=session_id,
            )
        except (RuntimeError, OSError, TimeoutError, ValueError) as exc:
            return ChairDecision(
                action="reply",
                message=(
                    f"{chair_label_for(agent)} 這一輪沒回成（{exc}）。"
                    "沒有開會，也沒有換成別人。可說：讓 Qwen 當主席"
                ),
                reason="cli chair error",
            )
        _remember_cli_session(state, bound_cmd, session_id, work_dir)
        return ChairDecision(action="reply", message=text, reason=f"cli:{cmd}")

    if agent.kind in {"ollama", "openai"}:
        return decide_chair(
            user_text,
            state,
            backend="openai",
            base_url=agent.base_url,
            model=agent.model,
            api_key="ollama" if agent.kind == "ollama" else None,
        )

    return decide_chair(user_text, state, backend="mock")


def _mock_chair_decide(user_text: str, force_convene: bool) -> ChairDecision:
    text = user_text.strip()
    if force_convene:
        return ChairDecision(
            action="convene",
            message="好，我召集目前偵測到的可用 Agent 全員開會。",
            goal=text,
            reason="user forced /council",
        )
    if _GREETING.match(text):
        return ChairDecision(
            action="reply",
            message=(
                "嗨，我是主席。其它席次現在都安靜待命。\n"
                "用人話說即可：讓 Codex 當主席；召集大家開會，評估 …；"
                "或先不要開會，只跟我聊。"
            ),
            reason="greeting",
        )
    # Never auto-convene from keywords (D4). Slash / NL parser owns convene.
    return ChairDecision(
        action="reply",
        message=(
            f"我收到了：「{text[:120]}{'…' if len(text) > 120 else ''}」\n"
            "目前只有我（主席）在回你，其它席次未發言。\n"
            "要正式多席時說「召集大家開會，評估 …」。"
        ),
        reason="chair-only default",
    )


def decide_chair(
    user_text: str,
    state: ChatState,
    *,
    backend: str = "mock",
    force_convene: bool = False,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
) -> ChairDecision:
    """Generate a chair-only reply. Convene is authorized by parse_intent, not the model."""
    text = user_text.strip()
    if not text:
        return ChairDecision(action="reply", message="（空訊息）", reason="empty")

    if backend in {"mock", "mock_v0"} or backend.startswith("mock"):
        return _mock_chair_decide(text, force_convene)

    if force_convene:
        return ChairDecision(
            action="convene",
            message="好，召集各席。",
            goal=text,
            reason="user forced /council",
        )

    runner = get_runner(
        "openai",
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    if not isinstance(runner, OpenAICompatibleSeatRunner):
        return _mock_chair_decide(text, force_convene)

    history_blob = "\n".join(f"{t.role}: {t.content}" for t in state.history[-12:])
    system = (
        "你是 mk-xinone 的「主席（Chair）」。使用者主要只跟你對話。\n"
        "其它席次預設安靜。你只能回覆，不能自行開會。\n"
        "規則：打招呼、閒聊、澄清、整理 → action=reply。\n"
        "只回一個 JSON 物件，不要 markdown：\n"
        '{"action":"reply","message":"給使用者看的話",'
        '"goal":null,"reason":"短理由"}\n'
    )
    user = f"Recent history:\n{history_blob or '(none)'}\n\nUser now:\n{text}\n"
    try:
        content = runner._chat(system, user)
        raw = _extract_json_object(content)
        message = str(raw.get("message") or "").strip() or "（主席無文字）"
        return ChairDecision(
            action="reply",
            message=message,
            goal=None,
            reason=str(raw.get("reason") or "model"),
        )
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError, KeyError, TypeError):
        return ChairDecision(
            action="reply",
            message="主席這邊模型暫時有問題，其它席次不會自動開會。稍後再試即可。",
            reason="chair model error → reply only",
        )


def chair_should_not_spam_seats(decision: ChairDecision) -> bool:
    return decision.action == "reply"
