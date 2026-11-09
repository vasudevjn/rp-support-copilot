"""Thin wrapper around the Anthropic SDK with a JSON file cache.

Every LLM output is cached, keyed by (prompt version, model, input), so reruns are
deterministic and judges see identical results. Re-calling requires refresh=True.
Sonnet 5.5 rejects a non-default temperature, so determinism comes from the cache.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from .config import CACHE, PROMPTS, ROOT, load_config

_lock = threading.Lock()


def _api_key() -> str | None:
    """Key from env / .env locally, or st.secrets on Streamlit Cloud."""
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key
    try:
        import streamlit as st
        return st.secrets.get("ANTHROPIC_API_KEY")  # type: ignore[attr-defined]
    except Exception:
        return None


def llm_available() -> bool:
    return bool(_api_key())


def load_prompt(name: str) -> tuple[str, str]:
    """Return (version, body). The first line of each prompt file is 'version: X'."""
    text = (PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    first, _, body = text.partition("\n")
    m = re.match(r"version:\s*(\S+)", first)
    return (m.group(1) if m else "unversioned", body.strip())


class JsonCache:
    """A dict persisted to cache/<filename>, sorted so diffs stay stable."""

    def __init__(self, filename: str):
        self.path: Path = CACHE / filename
        self.data: dict[str, Any] = {}
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))

    @staticmethod
    def key(*parts: str) -> str:
        return hashlib.sha256("␟".join(parts).encode("utf-8")).hexdigest()[:24]

    def get(self, k: str):
        return self.data.get(k)

    def set(self, k: str, v: Any) -> None:
        with _lock:
            self.data[k] = v

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            self.path.write_text(json.dumps(self.data, indent=1, sort_keys=True, ensure_ascii=False),
                                 encoding="utf-8")


def call_json(system: str, user: str, schema: dict) -> dict:
    """One Claude call that must return JSON matching `schema` (structured outputs)."""
    import anthropic

    cfg = load_config()["llm"]
    client = anthropic.Anthropic(api_key=_api_key())
    kwargs: dict[str, Any] = dict(
        model=cfg["model"],
        max_tokens=cfg["max_tokens"],
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": cfg["effort"],
                       "format": {"type": "json_schema", "schema": schema}},
    )
    if cfg.get("use_fallbacks"):
        # Server-side refusal fallback: a declined request is re-run on a fallback model.
        resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                           fallbacks="default", **kwargs)
    else:
        resp = client.messages.create(**kwargs)
    if resp.stop_reason == "refusal":
        raise RuntimeError("LLM refused the request")
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(f"No JSON in LLM output: {text[:200]}")
    return json.loads(m.group(0))
