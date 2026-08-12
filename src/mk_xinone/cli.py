"""xinone CLI — list presets, run mock council, show sessions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from mk_xinone import __version__
from mk_xinone.orchestrator import run_mock_council
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


def cmd_show(args: argparse.Namespace) -> int:
    path = Path(args.session_dir)
    if not path.is_absolute():
        # allow sessions/foo from repo root or cwd
        cand = Path.cwd() / path
        if not cand.exists() and (repo_root() / path).exists():
            path = repo_root() / path
        else:
            path = cand
    try:
        bundle = read_session(path)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write(format_session_show(bundle))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        preset = load_preset(args.preset)
    except (FileNotFoundError, ValueError) as e:
        print(str(e), file=sys.stderr)
        return 1
    out = Path(args.out) if args.out else None
    if out is not None and not out.is_absolute():
        out = Path.cwd() / out
    try:
        session_dir = run_mock_council(
            goal=args.goal,
            preset=preset,
            out_dir=out,
            sessions_root=sessions_dir(),
        )
    except Exception as e:
        print(f"run failed: {e}", file=sys.stderr)
        return 1
    print(f"preset:  {preset.get('id')}")
    print(f"status:  completed (mock_v0)")
    print(f"session: {session_dir}")
    print()
    print("提示：本輪為 mock 席位。完整 demo 請看：")
    print("  xinone show sessions/demo-repo-council-2026-08-12")
    print()
    bundle = read_session(session_dir)
    sys.stdout.write(format_session_show(bundle))
    return 0


def cmd_doctor(_: argparse.Namespace) -> int:
    root = repo_root()
    ok = True
    checks = [
        ("repo_root", root.is_dir()),
        ("presets/", presets_dir().is_dir()),
        ("sessions/demo", (sessions_dir() / "demo-repo-council-2026-08-12" / "meta.json").is_file()),
        ("council-lite.yaml", (presets_dir() / "council-lite.yaml").is_file()),
    ]
    for name, passed in checks:
        mark = "ok" if passed else "FAIL"
        print(f"[{mark}] {name}")
        ok = ok and passed
    print(f"version: {__version__}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xinone",
        description="mk-xinone — chat to run a council; sessions stay on disk",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("list-presets", help="List built-in presets")
    sp.set_defaults(func=cmd_list_presets)

    sp = sub.add_parser("show", help="Show a local session directory")
    sp.add_argument("session_dir", help="Path to sessions/<id>")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("run", help="Run a council (v0: mock seats)")
    sp.add_argument("goal", help="User goal / prompt")
    sp.add_argument(
        "--preset",
        default="council-lite",
        help="Preset id (default: council-lite)",
    )
    sp.add_argument("--out", default=None, help="Output session directory")
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("doctor", help="Check install / demo integrity")
    sp.set_defaults(func=cmd_doctor)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    code = args.func(args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
