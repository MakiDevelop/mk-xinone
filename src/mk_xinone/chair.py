"""Chair-first dialogue: other seats stay silent unless convened."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from mk_xinone.backends import get_runner
from mk_xinone.backends.openai_compatible import (
    OpenAICompatibleSeatRunner,
    _extract_json_object,
)

# Soft signals that a multi-seat council may help
_CONVENE_HINTS = re.compile(
    r"(評估|分析|審議|審一下|多角度|多席|開會|council|review|比較|優缺|要不要做|"
    r"值不值得|風險|架構|提案|方案|判決|BORROW|INSTALL|決策)",
    re.IGNORECASE,
)
_GREETING = re.compile(
    r"^(哈囉|嗨|你好|您好|hello|hi|hey|早安|午安|晚安|在嗎|嗨嗨)[\s\W]*$",
    re.IGNORECASE,
)


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


def _mock_chair_decide(user_text: str, force_convene: bool) -> ChairDecision:
    text = user_text.strip()
    if force_convene:
        return ChairDecision(
            action="convene",
            message=(
                "好，我召集目前偵測到的可用 Agent 全員開會。"
                "（主席以外各席現在才會發言。）"
            ),
            goal=text,
            reason="user forced /council",
        )
    if _GREETING.match(text):
        return ChairDecision(
            action="reply",
            message=(
                "嗨，我是主席。其它席次現在都安靜待命。\n"
                "你可以跟我聊需求、釐清目標；若要正式多席審議，說清楚要評估什麼，"
                "或下 `/council <目標>` 我再開會。\n"
                "（目前 backend=mock，閒聊也是規則回覆。）"
            ),
            reason="greeting",
        )
    if _CONVENE_HINTS.search(text) and len(text) >= 10:
        return ChairDecision(
            action="convene",
            message=(
                "這題適合多席審議。我現在依「可用 Agent 偵測」召集全員開會"
                "（角色會自動分配），閒聊時他們不會插話。"
            ),
            goal=text,
            reason="convene heuristics",
        )
    # Default: chair-only clarification, no seats
    return ChairDecision(
        action="reply",
        message=(
            f"我收到了：「{text[:120]}{'…' if len(text) > 120 else ''}」\n"
            "目前只有我（主席）在回你，其它席次未發言。\n"
            "若這是要正式評估／決策的題目，請再補一點背景，或直接：\n"
            "  /council <完整目標>\n"
            "我就開會。"
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
    """Chair decides: reply alone, or convene multi-seat council."""
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

    # Real model chair
    runner = get_runner(
        "openai",
        base_url=base_url,
        api_key=api_key,
        model=model,
    )
    if not isinstance(runner, OpenAICompatibleSeatRunner):
        return _mock_chair_decide(text, force_convene)

    history_blob = "\n".join(
        f"{t.role}: {t.content}" for t in state.history[-12:]
    )
    system = (
        "你是 mk-xinone 的「主席（Chair）」。使用者主要只跟你對話。\n"
        "其它席次（Architect/Analyst/Engineer 等）預設安靜，只有你決定開會才召集。\n"
        "規則：\n"
        "1. 打招呼、閒聊、澄清問題 → action=reply，自己用白話回答，不要開會。\n"
        "2. 使用者要求評估/審議/多角度/決策，或題目明顯需要多視角 → action=convene。\n"
        "3. 不確定時先 reply 問清楚，不要動不動開會。\n"
        "只回一個 JSON 物件，不要 markdown：\n"
        '{"action":"reply"|"convene","message":"給使用者看的話",'
        '"goal":"若 convene 則填開會目標否則 null","reason":"短理由"}\n'
    )
    user = (
        f"Recent history:\n{history_blob or '(none)'}\n\n"
        f"User now:\n{text}\n"
    )
    try:
        # Reuse internal chat without seat JSON schema for council seats
        content = runner._chat(system, user)
        raw = _extract_json_object(content)
        action = str(raw.get("action") or "reply").lower().strip()
        if action not in {"reply", "convene"}:
            action = "reply"
        message = str(raw.get("message") or "").strip() or "（主席無文字）"
        goal = raw.get("goal")
        goal_s = str(goal).strip() if goal else None
        if action == "convene" and not goal_s:
            goal_s = text
        return ChairDecision(
            action=action,
            message=message,
            goal=goal_s,
            reason=str(raw.get("reason") or "model"),
        )
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError, KeyError, TypeError):
        # Fail closed to chair-only, never surprise-convene on error
        return ChairDecision(
            action="reply",
            message=(
                "主席這邊模型暫時有問題，其它席次不會自動開會。\n"
                "你可以稍後重試，或用 `/council <目標>` 強制開會。"
            ),
            reason="chair model error → reply only",
        )


def chair_should_not_spam_seats(decision: ChairDecision) -> bool:
    return decision.action == "reply"
