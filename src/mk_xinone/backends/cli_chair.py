"""Headless CLI chair adapters (print/exec, no seat runner)."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from collections.abc import Callable, Sequence
from pathlib import Path

# cmd name on PATH → argv builder. No approval-bypass flags.
_CHAIR_CMDS = frozenset({"claude", "codex", "gemini", "grok"})
_LOGIN_HINTS = (
    "not logged in",
    "please run /login",
    "please run claude auth login",
    "auth required",
    "not authenticated",
)

Runner = Callable[[list[str], float], tuple[int, str, str]]

_probe_cache: dict[str, tuple[bool, str]] = {}


def has_cli_chair_recipe(cmd: str) -> bool:
    return cmd in _CHAIR_CMDS


_MEMORY_POLICY = (
    "記憶只走 AMH（amh latest / amh MCP）。"
    "禁止 Google Drive、Gmail、workspace-mcp、raw memhall HTTP。"
    "沒查到 AMH 就說查不到，不要改去外部雲端翻。"
)

_CHAIR_WORKSPACE_MD = """# xinone chair

你是 mk-xinone 的主席。只回白話。不要自己開會。

## 記憶

- 只查 AMH：`amh latest --ns personal` 或 MCP `amh`
- 禁止：Google Drive、Gmail、Docs、Sheets、raw memhall HTTP
- 查不到就說查不到

公司工作可再查 `amh latest --ns project:abd-ai-hub`（不要把公司內容寫進個人 ns）。
"""


def amh_mcp_config_path() -> Path:
    return Path(__file__).resolve().parent / "amh.mcp.json"


def write_chair_workspace(chair_dir: Path) -> Path:
    """Give each CLI chair a tiny policy workspace (AMH only)."""
    chair_dir.mkdir(parents=True, exist_ok=True)
    for name in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
        path = chair_dir / name
        if not path.exists():
            path.write_text(_CHAIR_WORKSPACE_MD, encoding="utf-8")
    mcp = chair_dir / "amh.mcp.json"
    src = amh_mcp_config_path()
    if src.is_file():
        mcp.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        mcp.write_text(
            '{"mcpServers":{"amh":{"command":"amh","args":["serve"]}}}\n',
            encoding="utf-8",
        )
    return mcp


def build_chair_prompt(label: str, user_text: str, history_blob: str) -> str:
    return (
        f"你是 mk-xinone 的主席（{label}）。\n"
        "只回使用者看的白話。不要 JSON、不要 markdown 圍欄、不要自己開會。\n"
        f"{_MEMORY_POLICY}\n"
        f"最近對話：\n{history_blob or '（無）'}\n\n"
        f"使用者現在說：\n{user_text.strip()}\n"
    )


def build_cli_chair_command(
    cmd: str,
    prompt: str,
    *,
    last_message_path: str | None = None,
    continue_session: bool = False,
    session_id: str | None = None,
    mcp_config: str | None = None,
) -> list[str]:
    if cmd == "claude":
        # Isolate from user MCP (Drive/Gmail). AMH only via --mcp-config.
        # Do not use --bare (ignores keychain) or --safe-mode (kills MCP).
        argv = [
            "claude",
            "-p",
            "--output-format",
            "text",
            "--permission-mode",
            "plan",
            "--effort",
            "low",
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--mcp-config",
            mcp_config or str(amh_mcp_config_path()),
        ]
        if continue_session and session_id:
            argv.extend(["--resume", session_id])
        elif session_id:
            argv.extend(["--session-id", session_id])
        argv.append(prompt)
        return argv
    if cmd == "codex":
        if continue_session:
            argv = [
                "codex",
                "exec",
                "resume",
                "--last",
                "--skip-git-repo-check",
                "-s",
                "read-only",
                "--color",
                "never",
            ]
        else:
            argv = [
                "codex",
                "exec",
                "--skip-git-repo-check",
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
        argv = [
            "gemini",
            "-p",
            prompt,
            "--approval-mode",
            "plan",
            "-o",
            "text",
            "--allowed-mcp-server-names",
            "amh",
        ]
        if continue_session:
            argv.extend(["--resume", "latest"])
        return argv
    if cmd == "grok":
        argv = ["grok"]
        if continue_session:
            argv.append("-c")
        argv.extend(
            [
                "-p",
                prompt,
                "--no-subagents",
                "--disable-web-search",
                "--output-format",
                "plain",
            ]
        )
        return argv
    raise ValueError(f"no chair recipe for {cmd!r}")


def new_cli_session_id() -> str:
    return str(uuid.uuid4())


def bind_cli_workspace(
    work_dir: str | None,
    cmd: str,
    prev_cmd: str | None,
    prev_session_id: str | None,
) -> tuple[str, bool, str, str]:
    """
    Isolate CLI chair from the user's cwd (often ~).

    Returns (work_dir, continue_session, session_id, cmd).
    """
    root = work_dir or tempfile.mkdtemp(prefix="xinone-chair-")
    chair_dir = Path(root) / cmd
    chair_dir.mkdir(parents=True, exist_ok=True)
    write_chair_workspace(chair_dir)
    if prev_cmd == cmd and prev_session_id:
        return root, True, prev_session_id, cmd
    return root, False, new_cli_session_id(), cmd


def login_hint(cmd: str) -> str:
    if cmd == "claude":
        return "未登入，請先執行：claude auth login"
    if cmd == "codex":
        return "未登入，請先執行：codex login"
    if cmd == "gemini":
        return "未登入，請先執行：gemini 登入"
    if cmd == "grok":
        return "未登入，請先執行：grok login"
    return "未登入"


def _looks_logged_out(text: str) -> bool:
    blob = (text or "").lower()
    return any(hint in blob for hint in _LOGIN_HINTS)


def parse_claude_auth_status(stdout: str) -> tuple[bool, str]:
    raw = (stdout or "").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        if _looks_logged_out(raw):
            return False, login_hint("claude")
        return False, login_hint("claude")
    if isinstance(data, dict) and data.get("loggedIn") is True:
        return True, ""
    return False, login_hint("claude")


def parse_codex_login_status(stdout: str, stderr: str = "", code: int = 0) -> tuple[bool, str]:
    text = f"{stdout}\n{stderr}"
    if "logged in" in text.lower():
        return True, ""
    if _looks_logged_out(text) or code != 0:
        return False, login_hint("codex")
    return False, login_hint("codex")


def probe_cli_chair_ready(
    cmd: str,
    *,
    runner: Runner | None = None,
    use_cache: bool = True,
) -> tuple[bool, str]:
    """Cheap auth probe. PATH-only is not enough (Claude --bare taught us that)."""
    if cmd not in _CHAIR_CMDS:
        return False, "尚無 chair adapter"
    if use_cache and cmd in _probe_cache:
        return _probe_cache[cmd]
    run = runner or _default_runner
    if cmd == "claude":
        try:
            code, out, err = run(["claude", "auth", "status", "--json"], 4.0)
        except (OSError, TimeoutError) as exc:
            result = (False, f"無法檢查登入：{exc}")
        else:
            result = parse_claude_auth_status(out or err)
            if code != 0 and result[0]:
                result = (False, login_hint("claude"))
    elif cmd == "codex":
        try:
            code, out, err = run(["codex", "login", "status"], 4.0)
        except (OSError, TimeoutError) as exc:
            result = (False, f"無法檢查登入：{exc}")
        else:
            result = parse_codex_login_status(out, err, code)
    else:
        # gemini / grok: no reliable cheap status; PATH + recipe is best we have
        result = (True, "")
    if use_cache:
        _probe_cache[cmd] = result
    return result


def _default_runner(
    argv: list[str],
    timeout: float,
    *,
    cwd: str | None = None,
) -> tuple[int, str, str]:
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
        cwd=cwd,
    )
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def run_cli_chair(
    cmd: str,
    prompt: str,
    *,
    timeout: float = 90.0,
    runner: Runner | None = None,
    cwd: str | None = None,
    continue_session: bool = False,
    session_id: str | None = None,
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
        mcp_config = None
        if cwd:
            cand = Path(cwd) / "amh.mcp.json"
            if cand.is_file():
                mcp_config = str(cand)
        argv = build_cli_chair_command(
            cmd,
            prompt,
            last_message_path=last_path,
            continue_session=continue_session,
            session_id=session_id,
            mcp_config=mcp_config,
        )

        def _run(run_argv: list[str], run_timeout: float) -> tuple[int, str, str]:
            if runner is not None:
                return runner(run_argv, run_timeout)
            return _default_runner(run_argv, run_timeout, cwd=cwd)

        code, stdout, stderr = _run(argv, timeout)
        combined = f"{stdout}\n{stderr}"
        if _looks_logged_out(combined):
            raise RuntimeError(login_hint(cmd))
        if code != 0:
            detail = combined.strip().splitlines()
            hint = detail[-1] if detail else f"exit {code}"
            raise RuntimeError(f"{cmd} chair failed: {hint[:200]}")
        if last_path:
            text = Path(last_path).read_text(encoding="utf-8").strip()
            if text:
                if _looks_logged_out(text):
                    raise RuntimeError(login_hint(cmd))
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
