"""Headless CLI chair adapters (print/exec, no seat runner)."""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

# cmd name on PATH → argv builder. No approval-bypass flags.
_CHAIR_CMDS = frozenset({"claude", "codex", "gemini", "grok"})

Runner = Callable[[list[str], float], tuple[int, str, str]]


def has_cli_chair_recipe(cmd: str) -> bool:
    return cmd in _CHAIR_CMDS


def build_chair_prompt(label: str, user_text: str, history_blob: str) -> str:
    return (
        f"你是 mk-xinone 的主席（{label}）。\n"
        "只回使用者看的白話。不要 JSON、不要 markdown 圍欄、不要開會、不要呼叫工具。\n"
        f"最近對話：\n{history_blob or '（無）'}\n\n"
        f"使用者現在說：\n{user_text.strip()}\n"
    )


def build_cli_chair_command(
    cmd: str,
    prompt: str,
    *,
    last_message_path: str | None = None,
) -> list[str]:
    if cmd == "claude":
        return [
            "claude",
            "-p",
            "--bare",
            "--tools",
            "",
            "--output-format",
            "text",
            "--no-session-persistence",
            prompt,
        ]
    if cmd == "codex":
        argv = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "-s",
            "read-only",
            "--color",
            "never",
        ]
        if last_message_path:
            argv.extend(["-o", last_message_path])
        argv.append(prompt)
        return argv
    if cmd == "gemini":
        return [
            "gemini",
            "-p",
            prompt,
            "--approval-mode",
            "plan",
            "-o",
            "text",
        ]
    if cmd == "grok":
        return [
            "grok",
            "-p",
            prompt,
            "--no-subagents",
            "--disable-web-search",
            "--output-format",
            "plain",
        ]
    raise ValueError(f"no chair recipe for {cmd!r}")


def _default_runner(argv: list[str], timeout: float) -> tuple[int, str, str]:
    env = os.environ.copy()
    env.setdefault("NO_COLOR", "1")
    env.setdefault("CLICOLOR", "0")
    proc = subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def run_cli_chair(
    cmd: str,
    prompt: str,
    *,
    timeout: float = 90.0,
    runner: Runner | None = None,
) -> str:
    """Run one headless chair turn. Raises RuntimeError on failure."""
    last_path: str | None = None
    tmp: tempfile.NamedTemporaryFile | None = None
    if cmd == "codex":
        tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
            prefix="xinone-chair-",
            suffix=".txt",
            delete=False,
        )
        last_path = tmp.name
        tmp.close()
    try:
        argv = build_cli_chair_command(cmd, prompt, last_message_path=last_path)
        code, stdout, stderr = (runner or _default_runner)(argv, timeout)
        if code != 0:
            detail = (stderr or stdout).strip().splitlines()
            hint = detail[-1] if detail else f"exit {code}"
            raise RuntimeError(f"{cmd} chair failed: {hint[:200]}")
        if last_path:
            text = Path(last_path).read_text(encoding="utf-8").strip()
            if text:
                return text
        text = stdout.strip()
        if not text:
            raise RuntimeError(f"{cmd} chair returned empty output")
        return text
    finally:
        if last_path:
            try:
                Path(last_path).unlink()
            except OSError:
                pass


def cli_cmd_from_agent_id(agent_id: str) -> str:
    if agent_id.startswith("cli:"):
        return agent_id.split(":", 1)[1]
    return agent_id


def cli_chair_commands() -> Sequence[str]:
    return tuple(sorted(_CHAIR_CMDS))
