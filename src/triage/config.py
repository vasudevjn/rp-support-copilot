"""Load config/rules.yaml and resolve project paths."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "rules.yaml"
OUTPUTS = ROOT / "outputs"
CACHE = ROOT / "cache"
PROMPTS = ROOT / "prompts"
TEMPLATES = ROOT / "templates"
EVAL = ROOT / "eval"


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    """Return the parsed rulebook. Cached for the process lifetime."""
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def team_name(key: str | None) -> str:
    """Map a team key (e.g. 'risk_ops') to its display name ('Risk Ops')."""
    if not key:
        return ""
    return load_config()["teams"][key]
