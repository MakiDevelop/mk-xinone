"""xinone CLI — list presets, run council, chair chat, show sessions, doctor."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from mk_xinone import __version__
from mk_xinone.agents import (
    build_all_hands_preset,
    discover_agents,
    format_agents_table,
    pick_default_chair_agent,
)
from mk_xinone.backends.openai_compatible import resolve_openai_settings
from mk_xinone.chair import (
    ChatState,
    ChatTurn,
    ConveneCard,
    apply_chair_change,
    assignment_from_agent,
    decide_chair,
    format_convene_card,
    parse_confirm_reply,
    parse_intent,
)
from mk_xinone.orchestrator import run_council
from mk_xinone.paths import presets_dir, repo_root, sessions_dir
from mk_xinone.presets import load_preset, summarize_presets
from mk_xinone.session_io import (
    format_session_show,
    latest_session,
    read_session,
)

_SUBCOMMANDS = frozenset(
    {"list-presets", "show", "agents", "run", "chat", "doctor"}
)
_HELP_FLAGS = frozenset({"-h", "--help", "--version"})


def cmd_list_presets(_: argparse.Namespace) -> int:
    rows = summarize_presets()
    if not rows:
        print("no presets found", file=sys.stderr)
        return 1
    for r in rows:
        print(f"{r['id']:16}  {r['name']}")
        if r["description"]:
            print(f"  {r['description']}")
    return 0


def cmd_agents(_: argparse.Namespace) -> int:
    disc = discover_agents()
    sys.stdout.write(format_agents_table(disc))
    return 0 if disc.runnable else 1


def _resolve_council_preset(args: argparse.Namespace) -> tuple[dict, object]:
    """
    Default: if any real runnable agents exist → all-hands (全員加入).
    Only mock available, or --no-all-agents → fixed preset (multi-role mock).
    """
    disc = discover_agents()
    no_all = getattr(args, "no_all_agents", False)
    real = [a for a in disc.runnable if a.kind != "mock"]
    if not no_all and real:
        preset = build_all_hands_preset(disc)
        return preset, disc
    return load_preset(args.preset), disc


def _resolve_session_path(raw: str) -> Path:
    path = Path(raw)
    if path.is_absolute():
        return path
    if raw in {"demo", "demo-repo-council"}:
        return sessions_dir() / "demo-repo-council-2026-08-12"
    cand = Path.cwd() / path
    if not cand.exists() and (repo_root() / path).exists():
        return repo_root() / path
    return cand


def cmd_show(args: argparse.Namespace) -> int:
    path = _resolve_session_path(args.session_dir)
    try:
        bundle = read_session(path)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write(format_session_show(bundle, verbose=args.verbose))
    return 0


def _print_run_result(session_dir: Path, *, verbose: bool) -> int:
    try:
        bundle = read_session(session_dir)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    meta = bundle["meta"]
    status = meta.get("status", "?")
    mode = meta.get("mode", "?")
    print()
    print(f"status:  {status}  mode={mode}")
    print(f"session: {session_dir}")
    if mode == "mock":
        print()
        print("*** MOCK 浮水印：非真實多模型。demo：xinone show demo ***")
    print()
    sys.stdout.write(format_session_show(bundle, verbose=verbose))
    if status == "completed":
        return 0
    if status == "blocked":
        return 3
    return 1


def _backend_kwargs(
    backend: str,
    args: argparse.Namespace,
) -> tuple[str, str | None, str | None, str | None]:
    """Return run_backend, base_url, api_key, model."""
    base_url, api_key, model = args.base_url, args.api_key, args.model
    run_backend = backend
    if backend == "ollama":
        run_backend = "openai"
        if not base_url and not os.environ.get("XINONE_BASE_URL"):
            base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434") + "/v1"
        if not model and not os.environ.get("XINONE_MODEL"):
            model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
        if api_key is None and not os.environ.get("XINONE_API_KEY"):
            api_key = os.environ.get("OPENAI_API_KEY", "ollama")
    return run_backend, base_url, api_key, model


def cmd_run(args: argparse.Namespace) -> int:
    try:
        preset, disc = _resolve_council_preset(args)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else None
    if out is not None and not out.is_absolute():
        out = Path.cwd() / out

    def progress(msg: str) -> None:
        print(f"… {msg}", flush=True)

    run_backend, base_url, api_key, model = _backend_kwargs(args.backend, args)
    # all-hands seats carry their own backend/model; default only fills gaps
    if preset.get("all_hands"):
        print(f"agents:  {disc.summary_line()} → all-hands ({len(preset.get('seats', []))} seats)")
        run_backend = "openai"  # per-seat overrides; ignore pure mock default

    try:
        session_dir = run_council(
            goal=args.goal,
            preset=preset,
            backend=run_backend if not preset.get("all_hands") else "mock",
            out_dir=out,
            sessions_root=sessions_dir(),
            force=args.force,
            on_progress=progress,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as e:
        print(f"run failed: {e}", file=sys.stderr)
        return 1

    print()
    print(f"preset:  {preset.get('id')}")
    return _print_run_result(session_dir, verbose=args.verbose)


def _chair_prompt(state: ChatState) -> str:
    if state.pending_confirm is not None:
        return "確認> "
    label = state.active_chair.label if state.active_chair else "主席"
    return f"{label}（主席）> "


def _print_chair(state: ChatState, message: str) -> None:
    label = state.active_chair.label if state.active_chair else "主席"
    print()
    print(f"{label}（主席）> {message}")
    print()


def _resolve_chat_preset(
    preset_id: str, args: argparse.Namespace
) -> tuple[dict, object]:
    class _Args:
        pass

    a = _Args()
    a.preset = preset_id
    a.no_all_agents = getattr(args, "no_all_agents", False)
    a.backend = getattr(args, "backend", "mock")
    return _resolve_council_preset(a)  # type: ignore[arg-type]


def _build_confirm_card(
    goal: str, state: ChatState, preset_id: str, args: argparse.Namespace
) -> ConveneCard | None:
    if state.active_chair is None:
        return None
    try:
        preset, _disc = _resolve_chat_preset(preset_id, args)
    except (FileNotFoundError, ValueError):
        preset = {"id": preset_id, "seats": []}
    n_seats = len(preset.get("seats") or [])
    roster = "all-hands" if preset.get("all_hands") else str(preset.get("id") or preset_id)
    return ConveneCard(
        goal=goal,
        chair=state.active_chair,
        seat_count=n_seats,
        roster_label=roster,
    )


def _show_confirm_card(card: ConveneCard) -> None:
    print()
    sys.stdout.write(format_convene_card(card))


def _run_confirmed_council(
    state: ChatState,
    *,
    preset_id: str,
    backend: str,
    args: argparse.Namespace,
    verbose: bool,
) -> int:
    card = state.pending_confirm
    if card is None or state.active_chair is None:
        return 0
    try:
        preset, disc = _resolve_chat_preset(preset_id, args)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        state.pending_confirm = None
        return 1

    run_backend, base_url, api_key, model = _backend_kwargs(backend, args)
    n_seats = len(preset.get("seats") or [])
    print(
        f"（開會中… {disc.summary_line()} → "
        f"{'all-hands' if preset.get('all_hands') else preset.get('id')} "
        f"{n_seats} seats）"
    )

    def progress(msg: str) -> None:
        print(f"… {msg}", flush=True)

    try:
        session_dir = run_council(
            goal=card.goal,
            preset=preset,
            backend=run_backend if not preset.get("all_hands") else "mock",
            sessions_root=sessions_dir(),
            on_progress=progress,
            base_url=base_url,
            api_key=api_key,
            model=model,
            chair=state.active_chair.to_meta(),
        )
    except (OSError, ValueError, RuntimeError, FileExistsError) as e:
        print(f"council failed: {e}", file=sys.stderr)
        state.pending_confirm = None
        return 1

    state.pending_confirm = None
    state.last_session_id = session_dir.name
    code = _print_run_result(session_dir, verbose=verbose)
    _print_chair(state, "會開完了。其它席次再次安靜；有需要再叫我開會。")
    return code


def cmd_chat(args: argparse.Namespace) -> int:
    """NL-first REPL: confirm card before convene; slash is an escape hatch."""
    disc0 = discover_agents()
    preferred = getattr(args, "chair", None)
    picked = pick_default_chair_agent(disc0.agents, preferred=preferred)
    fallback_note = ""
    if preferred and picked.status != "unique":
        fallback_note = (
            picked.message or f"無法指派 {preferred} 當主席"
        )
        picked = pick_default_chair_agent(disc0.agents)

    if picked.status != "unique" or picked.agent is None:
        print("沒有可主持的 agent（含 mock）。", file=sys.stderr)
        return 1

    chair = assignment_from_agent(picked.agent, source="default", turn=0)
    state = ChatState(default_chair=chair, active_chair=chair)
    if picked.agent.kind == "mock":
        print("目前沒有可主持的真實 agent，由 Mock 擔任主席。")
    print(f"主席：{chair.label}（可改：讓 Gemini 當主席）")
    if fallback_note:
        print(f"（--chair {preferred} 失敗：{fallback_note}；未靜默假裝已指派）")
    print(f"agents: {disc0.summary_line()}")
    print()
    print("人話例句：")
    print("  讓 Codex 當主席")
    print("  召集大家開會，評估 …")
    print("  有哪些 agent？誰能當主席？")
    print("  上一場會議怎樣？")
    print("  先不要開會，幫我整理三點")
    print()

    preset_id = args.preset
    backend = args.backend
    verbose = args.verbose
    last_code = 0

    def _remember(user_text: str, reply: str) -> None:
        state.history.append(ChatTurn(role="user", content=user_text))
        state.history.append(ChatTurn(role="chair", content=reply))
        state.turns += 1

    while True:
        try:
            line = input(_chair_prompt(state)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if state.pending_confirm is not None:
            action = parse_confirm_reply(line)
            if action == "confirm":
                last_code = _run_confirmed_council(
                    state,
                    preset_id=preset_id,
                    backend=backend,
                    args=args,
                    verbose=verbose,
                )
                continue
            if action == "cancel":
                state.pending_confirm = None
                msg = "已取消開會，只跟主席聊。"
                _print_chair(state, msg)
                _remember(line or "n", msg)
                last_code = 0
                continue
            if action == "appoint":
                plan = parse_intent(line)
                ok, msg = apply_chair_change(state, plan, discover_agents().agents)
                print(msg)
                if ok and state.active_chair is not None and state.pending_confirm:
                    state.pending_confirm.chair = state.active_chair
                    _show_confirm_card(state.pending_confirm)
                last_code = 0
                continue
            # chatter: drop confirm, treat as a new normal turn
            state.pending_confirm = None

        if not line:
            continue
        if line in {"/quit", "/exit", "/q", "quit", "exit"}:
            break
        if line.startswith("/preset"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                preset_id = parts[1].strip()
                print(f"preset → {preset_id}")
            else:
                print(f"current preset: {preset_id}")
            continue
        if line.startswith("/backend"):
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip() in {"mock", "openai", "ollama"}:
                backend = parts[1].strip()
                print(f"backend → {backend}")
            else:
                print(f"current backend: {backend} (mock|openai|ollama)")
            continue
        if line in {"/verbose", "/v"}:
            verbose = not verbose
            print(f"verbose → {verbose}")
            continue
        if line in {"/help", "help", "?"}:
            print("人話為主。slash 只是逃生口。")
            print("  讓 Codex 當主席 / 恢復預設主席")
            print("  召集大家開會，評估 <目標>")
            print("  有哪些 agent？ / 上一場會議怎樣？")
            print("進階：/council <目標>  /agents  /preset  /backend  /quit")
            continue
        if line in {"/agents", "/agent"}:
            sys.stdout.write(format_agents_table(discover_agents()))
            continue

        user_text = line
        slash_council = False
        if line.startswith("/council"):
            parts = line.split(maxsplit=1)
            user_text = parts[1].strip() if len(parts) == 2 else ""
            if not user_text:
                print("用法: /council <要審議的目標>（仍會先出確認卡）")
                continue
            slash_council = True

        agents = discover_agents().agents
        if slash_council:
            plan = parse_intent(f"召集大家開會，{user_text}")
            if plan.primary != "convene":
                plan.primary = "convene"
                plan.goal = user_text
                plan.explicit_multi_seat = True
                plan.reason = "slash /council"
        else:
            plan = parse_intent(user_text)

        if plan.primary == "exit":
            break

        if plan.chair_change != "keep":
            ok, msg = apply_chair_change(state, plan, agents)
            print(msg)
            if not ok and plan.primary == "convene":
                last_code = 0
                continue
            if plan.primary == "reply":
                last_code = 0
                continue

        if plan.stay_chat_only:
            state.convene_mode = "chat_only"

        if plan.primary == "list_agents":
            sys.stdout.write(format_agents_table(discover_agents()))
            last_code = 0
            continue

        if plan.primary == "show_last_session":
            latest = latest_session(sessions_dir())
            if latest is None:
                _print_chair(state, "還沒有會議 session。")
            else:
                try:
                    bundle = read_session(latest)
                    sys.stdout.write(format_session_show(bundle))
                except FileNotFoundError as e:
                    print(str(e), file=sys.stderr)
            last_code = 0
            continue

        if plan.primary == "clarify":
            q = plan.question or "能再說清楚一點嗎？"
            _print_chair(state, q)
            _remember(user_text, q)
            last_code = 0
            continue

        if plan.primary == "convene" and plan.goal:
            # explicit collective unlocks chat_only
            state.convene_mode = "normal"
            card = _build_confirm_card(plan.goal, state, preset_id, args)
            if card is None:
                _print_chair(state, "還沒有主席，無法開會。")
                last_code = 0
                continue
            state.pending_confirm = card
            _show_confirm_card(card)
            last_code = 0
            continue

        _run_backend, base_url, api_key, model = _backend_kwargs(backend, args)
        chair_backend = "mock" if backend == "mock" else "openai"
        decision = decide_chair(
            user_text,
            state,
            backend=chair_backend,
            force_convene=False,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        _print_chair(state, decision.message)
        if verbose and decision.reason:
            print(f"      (reason: {decision.reason})")
        _remember(user_text, decision.message)
        last_code = 0

    return last_code


def cmd_doctor(args: argparse.Namespace) -> int:
    ok = True
    checks: list[tuple[str, bool, str]] = []

    root = repo_root()
    checks.append(("repo_root", root.is_dir(), str(root)))
    checks.append(("presets/", presets_dir().is_dir(), str(presets_dir())))
    demo = sessions_dir() / "demo-repo-council-2026-08-12" / "meta.json"
    checks.append(("sessions/demo", demo.is_file(), str(demo)))
    checks.append(
        ("council-lite.yaml", (presets_dir() / "council-lite.yaml").is_file(), "preset")
    )

    cfg = resolve_openai_settings()
    key_set = bool(cfg["api_key"])
    checks.append(
        (
            "API key (XINONE_API_KEY/OPENAI_API_KEY)",
            True,
            "set" if key_set else "missing (ok for mock / local ollama)",
        )
    )
    checks.append(("base_url", True, cfg["base_url"]))
    checks.append(("model", True, cfg["model"]))

    disc = discover_agents()
    checks.append(
        (
            "runnable agents",
            bool(disc.runnable),
            disc.summary_line(),
        )
    )

    for name, passed, detail in checks:
        mark = "ok" if passed else "FAIL"
        if not passed:
            ok = False
        print(f"[{mark}] {name}: {detail}")

    if args.probe:
        print("… probing chat-capable endpoint (models list)…")
        url = f"{cfg['base_url'].rstrip('/')}/models"
        headers = {"User-Agent": "mk-xinone-doctor/0.1"}
        if cfg["api_key"]:
            headers["Authorization"] = f"Bearer {cfg['api_key']}"
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            n = len(data.get("data") or [])
            print(f"[ok] probe /models → HTTP 200, {n} models visible")
        except urllib.error.HTTPError as e:
            print(f"[FAIL] probe HTTP {e.code}: set key/base_url or use --backend mock")
            ok = False
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            print(f"[FAIL] probe: {e}")
            ok = False

    print(f"version: {__version__}")
    print("tip: 人話說「召集大家開會，評估 …」；slash /council 仍可用")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xinone",
        description="mk-xinone — chair chat + on-demand multi-seat council",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=False)

    sp = sub.add_parser("list-presets", help="List built-in presets")
    sp.set_defaults(func=cmd_list_presets)

    sp = sub.add_parser("show", help="Show a local session directory")
    sp.add_argument("session_dir", help="Path to sessions/<id> or 'demo'")
    sp.add_argument("--verbose", "-v", action="store_true", help="Full verdict.md")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("agents", help="List detected agents (runnable = join all-hands)")
    sp.set_defaults(func=cmd_agents)

    sp = sub.add_parser("run", help="Run a full multi-seat council (no chair gate)")
    sp.add_argument("goal", help="User goal / prompt")
    sp.add_argument("--preset", default="council-lite", help="Fixed preset if --no-all-agents")
    sp.add_argument(
        "--backend",
        default="mock",
        choices=["mock", "openai", "ollama"],
        help="Default backend when not all-hands (default: mock)",
    )
    sp.add_argument(
        "--no-all-agents",
        action="store_true",
        help="Do not auto all-hands; use --preset only",
    )
    sp.add_argument("--out", default=None, help="Output session directory")
    sp.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into a non-empty --out directory",
    )
    sp.add_argument("--base-url", default=None, help="OpenAI-compatible base URL")
    sp.add_argument("--api-key", default=None, help="API key (prefer env)")
    sp.add_argument("--model", default=None, help="Model id")
    sp.add_argument("--verbose", "-v", action="store_true")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser(
        "chat",
        help="Talk to Chair; other seats silent until council is convened",
    )
    sp.add_argument("--preset", default="council-lite")
    sp.add_argument(
        "--backend",
        default="mock",
        choices=["mock", "openai", "ollama"],
    )
    sp.add_argument(
        "--no-all-agents",
        action="store_true",
        help="When convening, use fixed --preset instead of all runnable agents",
    )
    sp.add_argument("--base-url", default=None)
    sp.add_argument("--api-key", default=None)
    sp.add_argument("--model", default=None)
    sp.add_argument("--verbose", "-v", action="store_true")
    sp.add_argument(
        "--chair",
        default=None,
        help="Startup chair label (e.g. Codex). Fails visibly if not chair_capable.",
    )
    sp.set_defaults(func=cmd_chat)

    sp = sub.add_parser("doctor", help="Check install / demo / API env")
    sp.add_argument(
        "--probe",
        action="store_true",
        help="HTTP probe base_url/models (needs network)",
    )
    sp.set_defaults(func=cmd_doctor)

    return p


def _apply_ollama_defaults(args: argparse.Namespace) -> None:
    if getattr(args, "backend", None) != "ollama":
        return
    if getattr(args, "func", None) is cmd_chat:
        return
    args.backend = "openai"
    if not getattr(args, "base_url", None) and not os.environ.get("XINONE_BASE_URL"):
        args.base_url = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434") + "/v1"
    if not getattr(args, "model", None) and not os.environ.get("XINONE_MODEL"):
        args.model = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
    if getattr(args, "api_key", None) is None and not os.environ.get("XINONE_API_KEY"):
        args.api_key = os.environ.get("OPENAI_API_KEY", "ollama")


def _default_to_chat(argv: list[str]) -> list[str]:
    if not argv:
        return ["chat"]
    if argv[0] in _SUBCOMMANDS or argv[0] in _HELP_FLAGS:
        return argv
    return ["chat", *argv]


def main(argv: list[str] | None = None) -> None:
    raw = list(sys.argv[1:] if argv is None else argv)
    raw = _default_to_chat(raw)
    parser = build_parser()
    args = parser.parse_args(raw)
    if not getattr(args, "func", None):
        args = parser.parse_args(["chat"])
    _apply_ollama_defaults(args)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
