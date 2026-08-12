"""Resolve repo-root relative paths."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return repository root (parent of src/)."""
    return Path(__file__).resolve().parents[2]


def presets_dir() -> Path:
    return repo_root() / "presets"


def sessions_dir() -> Path:
    return repo_root() / "sessions"
