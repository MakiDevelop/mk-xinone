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
from mk_xinone.backends.openai_compatible import resolve_openai_settings
from mk_xinone.chair import ChatState, ChatTurn, decide_chair
from mk_xinone.orchestrator import run_council
from mk_xinone.paths import presets_dir, repo_root, sessions_dir
from mk_xinone.presets import load_preset, summarize_presets
from mk_xinone.session_io import format_session_show, read_session


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
        preset = load_preset(args.preset)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1

    out = Path(args.out) if args.out else None
    if out is not None and not out.is_absolute():
        out = Path.cwd() / out

    def progress(msg: str) -> None:
        print(f"… {msg}", flush=True)

    run_backend, base_url, api_key, model = _backend_kwargs(args.backend, args)

    try:
        session_dir = run_council(
            goal=args.goal,
            preset=preset,
            backend=run_backend,
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


def cmd_chat(args: argparse.Namespace) -> int:
    """Chair-first REPL: only Chair speaks unless a council is convened."""
    print("mk-xinone chat — 你跟「主席」對話；其它席次預設安靜")
    print(f"preset={args.preset}  backend={args.backend}")
    print("指令: /council <目標>  強制開會")
    print("      /preset <id>  /backend mock|openai|ollama  /verbose  /quit")
    print()

    preset_id = args.preset
    backend = args.backend
    verbose = args.verbose
    last_code = 0
    state = ChatState()

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
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
            print("預設只跟主席聊。其它席次不會發言。")
            print("/council <目標> 才開會；/preset /backend /verbose /quit")
            continue

        force_convene = False
        user_text = line
        if line.startswith("/council"):
            force_convene = True
            parts = line.split(maxsplit=1)
            user_text = parts[1].strip() if len(parts) == 2 else ""
            if not user_text:
                print("用法: /council <要審議的目標>")
                continue

        run_backend, base_url, api_key, model = _backend_kwargs(backend, args)
        # decide_chair: mock uses "mock"; openai path needs openai
        chair_backend = "mock" if backend == "mock" else "openai"

        decision = decide_chair(
            user_text,
            state,
            backend=chair_backend,
            force_convene=force_convene,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )

        state.history.append(ChatTurn(role="user", content=user_text))
        state.turns += 1

        # Always show chair message first
        print()
        print(f"主席> {decision.message}")
        if verbose and decision.reason:
            print(f"      (reason: {decision.reason})")
        print()
        state.history.append(ChatTurn(role="chair", content=decision.message))

        if decision.action != "convene":
            # Other seats stay silent
            last_code = 0
            continue

        # Convene multi-seat — only now other seats speak
        try:
            preset = load_preset(preset_id)
        except (FileNotFoundError, ValueError) as e:
            print(str(e), file=sys.stderr)
            last_code = 1
            continue

        goal = (decision.goal or user_text).strip()
        print(f"（開會中… preset={preset_id} backend={backend}）")

        def progress(msg: str) -> None:
            print(f"… {msg}", flush=True)

        try:
            session_dir = run_council(
                goal=goal,
                preset=preset,
                backend=run_backend,
                sessions_root=sessions_dir(),
                on_progress=progress,
                base_url=base_url,
                api_key=api_key,
                model=model,
            )
        except (OSError, ValueError, RuntimeError, FileExistsError) as e:
            print(f"council failed: {e}", file=sys.stderr)
            last_code = 1
            continue

        last_code = _print_run_result(session_dir, verbose=verbose)
        print()
        print("主席> 會開完了。其它席次再次安靜；有需要再叫我開會。")
        print()

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
    print("tip: chat = 主席陪聊；/council 或明確審議題才開會")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xinone",
        description="mk-xinone — chair chat + on-demand multi-seat council",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list-presets", help="List built-in presets")
    sp.set_defaults(func=cmd_list_presets)

    sp = sub.add_parser("show", help="Show a local session directory")
    sp.add_argument("session_dir", help="Path to sessions/<id> or 'demo'")
    sp.add_argument("--verbose", "-v", action="store_true", help="Full verdict.md")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("run", help="Run a full multi-seat council (no chair gate)")
    sp.add_argument("goal", help="User goal / prompt")
    sp.add_argument("--preset", default="council-lite", help="Preset id")
    sp.add_argument(
        "--backend",
        default="mock",
        choices=["mock", "openai", "ollama"],
        help="Seat backend (default: mock)",
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
    sp.add_argument("--base-url", default=None)
    sp.add_argument("--api-key", default=None)
    sp.add_argument("--model", default=None)
    sp.add_argument("--verbose", "-v", action="store_true")
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


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    _apply_ollama_defaults(args)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
