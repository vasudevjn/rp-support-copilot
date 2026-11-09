"""Reply drafting: template with slots (code) -> optional LLM polish for language and tone only."""
from __future__ import annotations

import re
import threading
from functools import lru_cache

import yaml

from .config import TEMPLATES, load_config
from .extract import Extraction
from .llm import JsonCache, call_json, llm_available, load_prompt
from .rules import Decision

# Dashboard paths named in the KB; any that appear in a draft must survive polishing.
KB_PATHS = ["Dashboard > Settlements", "Dashboard > Account > KYC", "Dashboard > Settings > Bank Account",
            "Dashboard > Reports > Invoices", "Dashboard > Disputes"]

POLISH_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
    "additionalProperties": False,
}


@lru_cache(maxsize=1)
def templates() -> dict:
    """Merge every templates/*.yaml file. common.yaml also holds ack, sign-off and field names."""
    merged: dict = {"templates": {}}
    for p in sorted(TEMPLATES.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        for k, v in data.items():
            if k == "templates":
                for name, t in v.items():
                    t["file"] = p.name
                    merged["templates"][name] = t
            else:
                merged[k] = v
    return merged


def lang_key(language: str) -> str:
    return "hi" if language == "Hinglish" else "en"


def _join_fields(fields: list[str], lk: str) -> str:
    names = [templates()["field_names"][f][lk] for f in fields]
    if len(names) <= 1:
        return "".join(names)
    joiner = " aur " if lk == "hi" else " and "
    return ", ".join(names[:-1]) + joiner + names[-1]


def greeting_for(merchant: dict | None, language: str) -> str:
    """The fixed first line of every reply (config reply_style): 'Hi {business name} team,' or 'Hi,' with no ID."""
    style = load_config()["reply_style"]
    lk = lang_key(language)
    name = (merchant or {}).get("business_name")
    return style["greeting"][lk].format(name=name) if name else style["greeting_no_name"][lk]


def template_parts(decision: Decision, extraction: Extraction, merchant: dict | None = None) -> dict:
    """The pieces of a reply: greeting, empathy acknowledgement (upset tone only), body, sign-off, keep list."""
    lk = lang_key(extraction.language)
    tpl = templates()["templates"][decision.sub_case]
    slots = {k: ("" if v is None else str(v)) for k, v in decision.slots.items()}
    slots["fields"] = _join_fields(decision.missing_fields, lk)
    body = tpl[lk].format(**slots)
    ack = ""
    if extraction.tone in ("frustrated", "angry") and decision.sub_case != "threat":
        acks = templates()["ack"]
        ack = acks.get(decision.category, acks["default"])[lk]
    greeting = greeting_for(merchant, extraction.language)
    keep = [slots[k] for k in ("last_settlement_amount", "last_settlement_date", "expected_settlement_date",
                               "payment_id", "amount") if slots.get(k) and slots[k] in body]
    keep += [p for p in KB_PATHS if p in body]
    keep += [c for c in ("SIGNATURE_MISMATCH", "BAD_REQUEST_ERROR", "49900", "@example.com", "order_id|payment_id")
             if c in body]
    keep.append(greeting)
    return {"greeting": greeting, "ack": ack, "body": body, "signoff": templates()["signoff"][lk],
            "keep": sorted(set(keep))}


def assemble(parts: dict, with_ack: bool) -> str:
    text = (parts["ack"] + " " if with_ack and parts["ack"] else "") + parts["body"]
    return f"{parts['greeting']}\n{text}\n\n{parts['signoff']}"


def template_reply(decision: Decision, extraction: Extraction, merchant: dict | None = None) -> tuple[str, list[str]]:
    """The code-only reply (used offline, for threats, and as the fallback): greeting, the fixed category
    acknowledgement for upset merchants, the template body, sign-off. Returns (reply, values to keep)."""
    parts = template_parts(decision, extraction, merchant)
    return assemble(parts, with_ack=True), parts["keep"]


_cache: JsonCache | None = None
_cache_lock = threading.Lock()


def _get_cache() -> JsonCache:
    """One shared cache. The lock stops two pipeline threads each creating their own copy (and losing writes)."""
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = JsonCache("replies.json")
        return _cache


def save_cache() -> None:
    _get_cache().save()


def polish(draft: str, keep: list[str], language: str, tone: str, feedback: str = "",
           refresh: bool = False, offline: bool = False, ack_hint: str = "",
           fallback: str | None = None) -> tuple[str, str]:
    """LLM rewrite for language and tone. Returns (reply, source). Falls back to `fallback` (the full template
    reply, with the fixed acknowledgement) or the draft. For upset merchants the model writes its own one-line
    empathy sentence; `ack_hint` is the category acknowledgement offered as an idea, not a script."""
    cfg = load_config()["llm"]
    fb = fallback if fallback is not None else draft
    if not cfg.get("polish_replies"):
        return fb, "template"
    version, prompt = load_prompt("reply_polisher")
    cache = _get_cache()
    k = JsonCache.key(version, cfg["model"], draft, language, tone, feedback, ack_hint)
    hit = cache.get(k)
    if hit and not refresh and not offline:
        return hit["reply"], "cache"
    if offline or not llm_available():
        return fb, "template"
    user = (f"Language: {language}\nMerchant tone: {tone}\nKeep exactly: {keep}\n"
            + (f"Empathy idea for the opening sentence (rephrase freely): {ack_hint}\n" if ack_hint else "")
            + (f"Your previous attempt failed a safety check: {feedback}. Fix that.\n" if feedback else "")
            + f"\nDraft:\n{draft}")
    out = call_json(prompt, user, POLISH_SCHEMA)["reply"].strip()
    cache.set(k, {"prompt_version": version, "model": cfg["model"], "draft": draft, "reply": out})
    return out, "llm"
