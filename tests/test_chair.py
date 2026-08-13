from __future__ import annotations

from mk_xinone.chair import ChatState, decide_chair


def test_greeting_chair_only_no_convene():
    d = decide_chair("哈囉～", ChatState(), backend="mock")
    assert d.action == "reply"
    assert d.goal is None
    assert "主席" in d.message or "席次" in d.message


def test_council_force():
    d = decide_chair(
        "評估本地 session 當 SSOT",
        ChatState(),
        backend="mock",
        force_convene=True,
    )
    assert d.action == "convene"
    assert d.goal


def test_evaluate_hint_convenes():
    d = decide_chair(
        "請多角度評估：是否該做 mk-xinone 這個產品",
        ChatState(),
        backend="mock",
    )
    assert d.action == "convene"


def test_short_chat_stays_with_chair():
    d = decide_chair("那下一步怎麼用", ChatState(), backend="mock")
    assert d.action == "reply"
    assert d.goal is None
    assert "主席" in d.message or "席次" in d.message
    # not the pure greeting blurb alone as if user only said hi
    assert "那下一步怎麼用" in d.message or "開會" in d.message
