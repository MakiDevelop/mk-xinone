from __future__ import annotations

from pathlib import Path

from mk_xinone.paths import repo_root
from mk_xinone.session_io import format_session_show, read_session, slugify


def test_slugify_url():
    assert "url" in slugify("see https://github.com/foo/bar now")


def test_demo_session_readable():
    demo = repo_root() / "sessions" / "demo-repo-council-2026-08-12"
    bundle = read_session(demo)
    assert bundle["meta"]["preset"] == "council-lite"
    assert "architect" in bundle["seats"]
    text = format_session_show(bundle)
    assert "verdict" in text.lower() or "SHIP_SCAFFOLD" in text
