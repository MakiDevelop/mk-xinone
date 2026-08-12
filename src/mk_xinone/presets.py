"""Load council presets from YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from mk_xinone.paths import presets_dir


def list_preset_files() -> list[Path]:
    d = presets_dir()
    if not d.is_dir():
        return []
    return sorted(d.glob("*.yaml"))


def load_preset(preset_id: str) -> dict[str, Any]:
    path = presets_dir() / f"{preset_id}.yaml"
    if not path.is_file():
        known = ", ".join(p.stem for p in list_preset_files()) or "(none)"
        raise FileNotFoundError(f"preset not found: {preset_id!r}. known: {known}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "id" not in data:
        raise ValueError(f"invalid preset file: {path}")
    return data


def summarize_presets() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in list_preset_files():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows.append(
            {
                "id": str(data.get("id", path.stem)),
                "name": str(data.get("name", path.stem)),
                "description": str(data.get("description", "")),
            }
        )
    return rows
