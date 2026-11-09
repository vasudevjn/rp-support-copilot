"""Extract structured fields from a ticket: regex for facts, LLM (or keywords) for reading.

Regex always owns IDs, amounts and day counts. The LLM reads category, language,
tone, threat type and vagueness. If no API key is set and nothing is cached, an
offline keyword reader (config-driven) fills those fields instead.
"""
from __future__ import annotations

import re
import threading
from dataclasses import asdict, dataclass, field

from .config import load_config
from .llm import JsonCache, call_json, llm_available, load_prompt

MID_RE = re.compile(r"\bM\d{4}\b")
PAY_RE = re.compile(r"\bpay_[A-Za-z0-9]+\b")
# Amounts: "Rs 2,50,000", "₹2.5L", "Rs 50k", "2 lakh", "1.5 crore", "12000 rupees".
_NUM = r"(\d[\d,]*(?:\.\d+)?)"
_UNIT = r"(lakhs?|lacs?|l|k|thousand|crores?|cr)\b"
AMOUNT_PREFIX_RE = re.compile(rf"(?:\brs\.?|₹|\binr)\s*{_NUM}(?:\s*{_UNIT})?", re.I)
AMOUNT_UNIT_RE = re.compile(rf"\b{_NUM}\s*(lakhs?|lacs?|crores?|rupees|rupaye|rs\b)", re.I)
UNIT_MULT = {"lakh": 100_000, "lac": 100_000, "l": 100_000, "k": 1_000, "thousand": 1_000,
             "crore": 10_000_000, "cr": 10_000_000}
# Ages: "6 days", "3 din", "2 weeks", "ek hafta", "a month".
AGE_RE = re.compile(r"\b(\d+|a|an|one|ek)\s*(days?|din|weeks?|hafte|hafta|months?|mahine|mahina)\b", re.I)
AGE_MULT = {"day": 1, "din": 1, "week": 7, "hafte": 7, "hafta": 7, "month": 30, "mahine": 30, "mahina": 30}


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def parse_amounts(message: str) -> list[float]:
    """Every rupee amount in the message, in rupees, with lakh / crore / k units applied."""
    text = PAY_RE.sub(" ", message)
    out: list[float] = []
    for m in AMOUNT_PREFIX_RE.finditer(text):
        unit = (m.group(2) or "").lower().rstrip("s")
        out.append(_to_float(m.group(1)) * UNIT_MULT.get(unit, 1))
    for m in AMOUNT_UNIT_RE.finditer(text):
        unit = m.group(2).lower().rstrip("s")
        val = _to_float(m.group(1)) * UNIT_MULT.get(unit, 1)
        if val not in out:
            out.append(val)
    return out


def parse_age_days(message: str) -> int | None:
    """Age of the request in calendar days; weeks count as 7 days and months as 30."""
    m = AGE_RE.search(PAY_RE.sub(" ", message))
    if not m:
        return None
    n = 1 if m.group(1).lower() in ("a", "an", "one", "ek") else int(m.group(1))
    unit = m.group(2).lower()
    unit = unit if unit in AGE_MULT else unit.rstrip("s")
    return n * AGE_MULT[unit]

EXTRACTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "language": {"type": "string", "enum": ["English", "Hinglish"]},
        "tone": {"type": "string", "enum": ["calm", "frustrated", "angry"]},
        "threat_type": {"type": "string", "enum": ["none", "legal_threat", "regulator", "fraud_allegation",
                                                   "bribery", "media_threat", "data_leak", "account_takeover"]},
        "is_vague": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": ["category", "language", "tone", "threat_type", "is_vague", "summary"],
    "additionalProperties": False,
}


@dataclass
class Extraction:
    merchant_id_in_message: str | None
    payment_id: str | None
    amount_inr: float | None
    days_ago: int | None
    intent: str | None             # from config intent patterns
    intent_category: str | None
    category: str                  # category before the threat override
    language: str
    tone: str
    urgent: bool
    threat_keywords: list[str]
    threat_type: str               # 'none' or a type name
    is_vague: bool
    summary: str
    source: str                    # 'llm', 'cache' or 'offline'
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- regex facts

def regex_facts(message: str) -> dict:
    mids = MID_RE.findall(message)
    pay = PAY_RE.search(message)
    amounts = parse_amounts(message)
    return {
        "merchant_id_in_message": mids[0] if mids else None,
        "payment_id": pay.group(0) if pay else None,
        # The largest amount wins: the refund threshold check (KB-07) must never see a smaller figure.
        "amount_inr": max(amounts) if amounts else None,
        "days_ago": parse_age_days(message),
    }


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def strip_ids(message: str) -> str:
    t = PAY_RE.sub(" ", message)
    t = re.sub(r"\b(merchant id|merchant|mid)\s*M\d{4}\b\.?", " ", t, flags=re.I)
    t = MID_RE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def word_count(message: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", strip_ids(message)))


# ---------------------------------------------------------------- keyword reading

def match_intent(message: str) -> tuple[str | None, str | None]:
    for it in load_config()["intents"]:
        if _any(it["patterns"], message):
            return it["name"], it["category"]
    return None, None


def threat_keywords(message: str) -> list[str]:
    """Whole-word, case-insensitive matches against the threat keyword list."""
    kws = load_config()["threats"]["keywords"]
    return [k for k in kws if re.search(rf"\b{re.escape(k)}\b", message, re.I)]


def threat_type_from_keywords(message: str) -> str:
    for t in load_config()["threats"]["types"]:
        if any(re.search(rf"\b{re.escape(k)}\b", message, re.I) for k in t["keywords"]):
            return t["name"]
    return "none"


def detect_language(message: str) -> str:
    cfg = load_config()["language"]
    words = set(re.findall(r"[a-z]+", strip_ids(message).lower()))
    hits = sum(1 for m in cfg["hinglish_markers"] if m in words)
    return "Hinglish" if hits >= cfg["min_markers"] else "English"


def detect_tone(message: str) -> str:
    cfg = load_config()["tone"]
    if _any(cfg["angry_patterns"], message):
        return "angry"
    if _any(cfg["frustrated_patterns"], message):
        return "frustrated"
    return "calm"


def is_urgent(message: str) -> bool:
    return _any(load_config()["tone"]["urgent_patterns"], message)


def offline_reading(message: str) -> dict:
    _, cat = match_intent(message)
    vague = word_count(message) <= load_config()["thresholds"]["vague_max_words"]
    return {
        "category": cat or ("Legal / Security" if threat_keywords(message) else "Unclear"),
        "language": detect_language(message),
        "tone": detect_tone(message),
        "threat_type": threat_type_from_keywords(message),
        "is_vague": vague,
        "summary": strip_ids(message)[:120],
    }


# ---------------------------------------------------------------- LLM reading (cached)

_cache: JsonCache | None = None
_cache_lock = threading.Lock()


def _get_cache() -> JsonCache:
    """One shared cache. The lock stops two pipeline threads each creating their own copy (and losing writes)."""
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = JsonCache("extractions.json")
        return _cache


def llm_reading(message: str, refresh: bool = False, offline: bool = False) -> tuple[dict | None, str]:
    """Return (reading, source). Uses the cache first; calls the API only if allowed."""
    cfg = load_config()["llm"]
    version, prompt = load_prompt("extractor")
    cache = _get_cache()
    k = JsonCache.key(version, cfg["model"], message)
    hit = cache.get(k)
    if hit and not refresh and not offline:
        return hit["reading"], "cache"
    if offline or not llm_available():
        return None, "offline"
    reading = call_json(prompt, f"Ticket message:\n{message}", EXTRACTOR_SCHEMA)
    cache.set(k, {"prompt_version": version, "model": cfg["model"], "message": message, "reading": reading})
    return reading, "llm"


def save_cache() -> None:
    _get_cache().save()


# ---------------------------------------------------------------- main entry

def extract(message: str, refresh: bool = False, offline: bool = False) -> Extraction:
    cfg = load_config()
    facts = regex_facts(message)
    notes: list[str] = []
    kw_intent, kw_cat = match_intent(message)
    kws = threat_keywords(message)
    kw_vague = word_count(message) <= cfg["thresholds"]["vague_max_words"]

    reading, source = None, "offline"
    try:
        reading, source = llm_reading(message, refresh=refresh, offline=offline)
    except Exception as e:  # network, refusal, bad JSON: fail safe to the keyword reader
        notes.append(f"LLM extractor failed, keyword reader used ({type(e).__name__})")
    if reading is None:
        reading = offline_reading(message)
        source = "offline"

    llm_cat = reading.get("category") if reading.get("category") in cfg["categories"] else None
    # Category: auditable intent patterns first; the LLM covers messages no pattern knows.
    category = kw_cat or llm_cat or "Unclear"
    if source != "offline" and kw_cat and llm_cat and kw_cat != llm_cat:
        notes.append(f"Category disagreement: patterns={kw_cat}, LLM={llm_cat}; patterns kept")

    # Threat: fail safe, either source fires.
    llm_threat = reading.get("threat_type") or "none"
    valid_types = {t["name"] for t in cfg["threats"]["types"]}
    kw_type = threat_type_from_keywords(message)
    if kw_type != "none":
        threat_type = kw_type
    elif llm_threat in valid_types:
        threat_type = llm_threat
        notes.append(f"Threat flagged by LLM only ({llm_threat}); keyword list missed it")
    elif str(llm_threat).strip().lower() not in ("none", "", "null"):
        # Fail safe: an unknown threat label still escalates, it is never silently dropped.
        threat_type = cfg["threats"]["unknown_type_fallback"]
        notes.append(f"LLM returned unknown threat type '{llm_threat}'; treated as {threat_type}")
    else:
        threat_type = "none"

    is_vague = kw_vague or (kw_intent is None and bool(reading.get("is_vague")))
    tone = reading.get("tone") if reading.get("tone") in ("calm", "frustrated", "angry") else detect_tone(message)
    language = (reading.get("language") if reading.get("language") in ("English", "Hinglish")
                else detect_language(message))

    return Extraction(
        merchant_id_in_message=facts["merchant_id_in_message"],
        payment_id=facts["payment_id"],
        amount_inr=facts["amount_inr"],
        days_ago=facts["days_ago"],
        intent=kw_intent,
        intent_category=kw_cat,
        category=category,
        language=language,
        tone=tone,
        urgent=is_urgent(message),
        threat_keywords=kws,
        threat_type=threat_type,
        is_vague=is_vague,
        summary=reading.get("summary", ""),
        source=source,
        notes=notes,
    )
