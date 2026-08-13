"""OpenAI-compatible chat completions seat runner (stdlib only)."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from mk_xinone.backends.base import SeatRequest, SeatResult
from mk_xinone.session_io import redact_secrets


def resolve_openai_settings(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    return {
        "base_url": (
            base_url
            or os.environ.get("XINONE_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/"),
        "api_key": api_key
        or os.environ.get("XINONE_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "",
        "model": model
        or os.environ.get("XINONE_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "gpt-4o-mini",
        "timeout": float(
            timeout
            if timeout is not None
            else os.environ.get("XINONE_TIMEOUT", "120")
        ),
    }


def _host_label(base_url: str) -> str:
    try:
        return urlparse(base_url).netloc or "openai"
    except (TypeError, ValueError):
        return "openai"


def _extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        data = json.loads(text[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError("model response is not a JSON object")


class OpenAICompatibleSeatRunner:
    name = "openai"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        transport: Any | None = None,
    ) -> None:
        cfg = resolve_openai_settings(
            base_url=base_url, api_key=api_key, model=model, timeout=timeout
        )
        self.base_url = cfg["base_url"]
        self.api_key = cfg["api_key"]
        self.model = cfg["model"]
        self.timeout = cfg["timeout"]
        self._transport = transport  # injectable for tests: callable(url, body, headers)->dict

    def run_seat(self, request: SeatRequest) -> SeatResult:
        actor = f"openai:{_host_label(self.base_url)}:{self.model}"

        system, user = self._prompts(request)
        try:
            content = self._chat(system, user)
            raw = _extract_json_object(content)
            payload = self._normalize_payload(request, raw)
            log = redact_secrets(
                f"[openai] seat={request.seat_id} model={self.model} ok\n"
            )
            return SeatResult(ok=True, payload=payload, log=log, actor=actor)
        except (RuntimeError, ValueError, OSError, json.JSONDecodeError, KeyError, TypeError) as e:
            err = redact_secrets(str(e))
            payload = {
                "schema": "mk-xinone.seat.v1",
                "id": request.seat_id,
                "role": request.role,
                "status": "failed",
                "one_line_verdict": f"seat failed: {err[:180]}",
                "key_points": [],
                "risks": [err[:300]],
                "confidence": 1,
            }
            log = redact_secrets(
                f"[openai] seat={request.seat_id} model={self.model} error={err}\n"
            )
            return SeatResult(ok=False, payload=payload, log=log, error=err, actor=actor)

    def _prompts(self, request: SeatRequest) -> tuple[str, str]:
        if request.kind == "synthesizer":
            system = (
                "You are the explicit Synthesizer seat of a multi-agent council. "
                "You only use peer seat structured outputs. Do not invent facts. "
                "Reply with a single JSON object only."
            )
            peers = json.dumps(request.peer_summaries, ensure_ascii=False, indent=2)
            user = (
                f"Goal:\n{request.goal}\n\n"
                f"Mission: {request.mission}\n\n"
                f"Peer seats (JSON):\n{peers}\n\n"
                "Return JSON with keys: one_line_verdict (string), key_points (array of strings), "
                "risks (array), confidence (1-5 int), verdict_label (string), "
                "consensus (array of strings), disagreements (array of "
                '{ "topic", "a", "b", "summary" }), blind_spots (array of strings).'
            )
            return system, user

        system = (
            f"You are the {request.role} seat in a multi-agent council. "
            "Be concrete and skeptical. Reply with a single JSON object only."
        )
        user = (
            f"Goal:\n{request.goal}\n\n"
            f"Your mission: {request.mission or '(none)'}\n\n"
            "Return JSON with keys: one_line_verdict (string), key_points (array of strings), "
            "risks (array of strings), confidence (1-5 int). "
            "If you are a Reviewer, also include verdict: PASS|FAIL|PASS_WITH_NITS "
            "and evidence (array of strings)."
        )
        return system, user

    def _normalize_payload(self, request: SeatRequest, raw: dict[str, Any]) -> dict[str, Any]:
        conf = raw.get("confidence", 3)
        try:
            conf_i = int(conf)
        except (TypeError, ValueError):
            conf_i = 3
        conf_i = max(1, min(5, conf_i))
        payload: dict[str, Any] = {
            "schema": "mk-xinone.seat.v1",
            "id": request.seat_id,
            "role": request.role,
            "status": "done",
            "one_line_verdict": str(raw.get("one_line_verdict") or raw.get("summary") or "")[:500],
            "key_points": list(raw.get("key_points") or [])[:12],
            "risks": list(raw.get("risks") or [])[:12],
            "confidence": conf_i,
        }
        if not payload["one_line_verdict"]:
            payload["one_line_verdict"] = f"{request.role}: (empty model one_line_verdict)"
        for k in ("verdict", "verdict_label", "evidence", "consensus", "disagreements", "blind_spots"):
            if k in raw:
                payload[k] = raw[k]
        return payload

    def _chat(self, system: str, user: str) -> str:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.3,
        }
        # Prefer JSON mode when supported; ignore if server rejects (caller may retry not needed)
        body["response_format"] = {"type": "json_object"}

        if self._transport is not None:
            data = self._transport(self.base_url, body, self.api_key)
            return self._content_from_response(data)

        url = f"{self.base_url}/chat/completions"
        data_bytes = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "mk-xinone/0.1",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            # Retry without response_format if server rejects it
            if e.code in {400, 404, 422} and "response_format" in body:
                body.pop("response_format", None)
                data_bytes = json.dumps(body).encode("utf-8")
                req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        raw = resp.read().decode("utf-8")
                except urllib.error.HTTPError as e2:
                    detail2 = e2.read().decode("utf-8", errors="replace")[:500]
                    raise RuntimeError(f"HTTP {e2.code}: {redact_secrets(detail2)}") from e2
            else:
                raise RuntimeError(f"HTTP {e.code}: {redact_secrets(detail)}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"connection failed: {e.reason}") from e

        data = json.loads(raw)
        return self._content_from_response(data)

    @staticmethod
    def _content_from_response(data: dict[str, Any]) -> str:
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("empty choices from chat/completions")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            # some servers return content parts
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
                elif isinstance(part, str):
                    parts.append(part)
            content = "".join(parts)
        if not content:
            raise RuntimeError("empty message content")
        return str(content)
