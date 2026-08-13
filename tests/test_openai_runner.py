from __future__ import annotations

import json

from mk_xinone.backends.base import SeatRequest
from mk_xinone.backends.openai_compatible import OpenAICompatibleSeatRunner


def test_openai_runner_with_fake_transport():
    def transport(base_url, body, api_key):
        assert body["model"] == "test-model"
        assert base_url.endswith("/v1") or "example" in base_url

        content = json.dumps(
            {
                "one_line_verdict": "fake seat ok",
                "key_points": ["a", "b"],
                "risks": ["r"],
                "confidence": 4,
            }
        )
        return {
            "choices": [{"message": {"content": content}}],
        }

    runner = OpenAICompatibleSeatRunner(
        base_url="http://example.test/v1",
        api_key="sk-test",
        model="test-model",
        transport=transport,
    )
    result = runner.run_seat(
        SeatRequest(goal="g", seat_id="architect", role="Architect", mission="m")
    )
    assert result.ok
    assert result.payload["one_line_verdict"] == "fake seat ok"
    assert result.payload["confidence"] == 4
    assert "openai:" in result.actor


def test_openai_runner_malformed():
    def transport(base_url, body, api_key):
        return {"choices": [{"message": {"content": "not-json-at-all"}}]}

    runner = OpenAICompatibleSeatRunner(
        base_url="http://example.test/v1",
        api_key="x",
        model="m",
        transport=transport,
    )
    result = runner.run_seat(
        SeatRequest(goal="g", seat_id="a", role="A")
    )
    assert not result.ok
    assert result.payload["status"] == "failed"
