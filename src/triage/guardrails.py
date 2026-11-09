"""Guardrail checker (pure Python). Every reply is checked before it can be sent.

Each check returns a list of failure reasons; an empty list means the check passed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import load_config
from .extract import detect_language, parse_amounts
from .load import load_kb

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
DATE_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON}(?:,?\s+(\d{{4}}))?\b", re.I)
DATE_MDY = re.compile(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.I)
DATE_NUM = re.compile(r"\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b|\b\d{1,2}-\d{1,2}-\d{2,4}\b")  # "5-7" is a range
DURATION = re.compile(
    r"\b(\d+(?:\s*-\s*\d+)?)\s+(additional\s+)?(business days?|calendar days?|days?|din|hours?|ghante|seconds?|"
    r"months?|mahine|weeks?|minutes?)\b|\bT\+\d+\b|\b\d+(?:st|nd|rd|th)\b", re.I)
ID_TOKENS = re.compile(r"\bpay_[A-Za-z0-9]+\b|\bM\d{4}\b|\bT-\d{4}\b|@example\.com")
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


@dataclass
class GuardrailResult:
    passed: bool
    failures: list[str] = field(default_factory=list)
    checks: dict[str, str] = field(default_factory=dict)   # check name -> PASS / FAIL: reason


def _norm_duration(s: str) -> str:
    s = re.sub(r"\s*-\s*", "-", s.lower().strip())
    s = re.sub(r"\s+", " ", s)
    s = s.replace("ghante", "hours").replace("mahine", "months").replace(" din", " days")
    s = re.sub(r"\bday\b", "days", s).replace("business days", "business days")
    if s == "1 business days":
        s = "1 business day"
    return s


def _date_key(day: str, mon: str) -> tuple[int, int]:
    return int(day), MONTHS[mon[:3].lower()]


def allowed_dates(merchant: dict | None) -> set[tuple[int, int]]:
    out = set()
    for f in ("last_settlement_date", "expected_settlement_date"):
        v = (merchant or {}).get(f)
        if v:
            d, m, _ = v.split()
            out.add(_date_key(d, m))
    return out


def check_dates(reply: str, merchant: dict | None) -> list[str]:
    allowed = allowed_dates(merchant)
    fails = []
    for m in DATE_DMY.finditer(reply):
        if _date_key(m.group(1), m.group(2)) not in allowed:
            fails.append(f"date '{m.group(0)}' is not in the merchant record")
    for m in DATE_MDY.finditer(reply):
        if _date_key(m.group(2), m.group(1)) not in allowed:
            fails.append(f"date '{m.group(0)}' is not in the merchant record")
    for m in DATE_NUM.finditer(reply):
        fails.append(f"numeric date '{m.group(0)}' not allowed")
    return fails


def find_durations(reply: str) -> list[str]:
    text = ID_TOKENS.sub(" ", reply)
    return [_norm_duration(m.group(0)) for m in DURATION.finditer(text)]


def check_durations(reply: str, kb_ids: list[str], action: str) -> list[str]:
    found = find_durations(reply)
    if action == "escalate":
        return [f"escalation reply contains a duration '{d}'" for d in found]
    table = load_config()["guardrails"]["allowed_durations"]
    allowed = {d for kb in kb_ids for d in table.get(kb, [])}
    return [f"duration '{d}' is not backed by cited KB {kb_ids}" for d in found if d not in allowed]


def _numbers(text: str) -> set[float]:
    out = set()
    for tok in NUMBER.findall(text):
        try:
            out.add(float(tok.replace(",", "")))
        except ValueError:
            pass
    return out


def check_numbers(reply: str, message: str, merchant: dict | None, kb_ids: list[str]) -> list[str]:
    kb = load_kb()
    text = ID_TOKENS.sub(" ", reply)
    text = DATE_DMY.sub(" ", text)
    text = DATE_MDY.sub(" ", text)
    allowed = _numbers(ID_TOKENS.sub(" ", message))
    allowed |= set(parse_amounts(message))                     # "2 lakh" -> 200000
    allowed |= {n * 100 for n in list(allowed)}               # rupees to paise (KB-12)
    for v in (merchant or {}).values():
        if isinstance(v, (int, float)):
            allowed.add(float(v))
        elif isinstance(v, str):
            allowed |= _numbers(v)
    for k in kb_ids:
        if k in kb:
            allowed |= _numbers(kb[k]["guidance"]) | _numbers(k)
    return [f"number '{n:g}' does not come from the ticket, merchant record or cited KB"
            for n in sorted(_numbers(text)) if n not in allowed]


def check_promises(reply: str) -> list[str]:
    low = reply.lower()
    return [f"promise phrase '{p}'" for p in load_config()["guardrails"]["promise_phrases"] if p in low]


def check_apology(reply: str) -> list[str]:
    """No apology in any reply. The category acknowledgement carries the empathy; an apology can imply fault."""
    low = reply.lower()
    return [f"apology '{p}' (use the acknowledgement line, no apology)"
            for p in load_config()["guardrails"]["apology_phrases"] if p in low]


def check_internal_reasons(reply: str, merchant: dict | None, sub_case: str) -> list[str]:
    if sub_case != "settlement_hold_escalate":
        return []
    terms = list(load_config()["guardrails"]["internal_reason_terms"])
    if merchant and merchant.get("hold_reason"):
        terms.append(merchant["hold_reason"].lower())
    low = reply.lower()
    return [f"internal reason term '{t}' shared" for t in terms if re.search(rf"\b{re.escape(t)}\b", low)]


def check_threat(reply: str, sub_case: str, send_mode: str) -> list[str]:
    if sub_case != "threat":
        return []
    low = reply.lower()
    fails = [f"threat reply contains '{p}'" for p in load_config()["guardrails"]["threat_banned_phrases"] if p in low]
    if send_mode != "do_not_send":
        fails.append("threat reply is not marked do_not_send")
    return fails


def check_ask_info(reply: str, action: str, missing_fields: list[str]) -> list[str]:
    if action != "ask_info":
        return []
    phrases = load_config()["guardrails"]["ask_info_field_phrases"]
    low = reply.lower()
    return [f"ask-info reply does not request '{f}'" for f in missing_fields
            if not any(p in low for p in phrases.get(f, [f]))]


LARGE_UNIT_RE = re.compile(r"\d\s*(lakhs?|lacs?|l|crores?|cr)\b", re.I)
REFUND_TIMELINE_RE = re.compile(r"\b5\s*-\s*7\b|\bbusiness days?\b|\bARN\b", re.I)


def check_refund_timeline(reply: str, message: str, sub_case: str) -> list[str]:
    """KB-07 backstop, independent of the rules engine: a refund reply that gives a timeline must not answer
    a message that names Rs 1,00,000 or more (as a raw figure or in lakh / crore units)."""
    if not sub_case.startswith("refund") or not REFUND_TIMELINE_RE.search(reply):
        return []
    thr = load_config()["thresholds"]["refund_manual_approval_inr"]
    text = ID_TOKENS.sub(" ", message)
    if LARGE_UNIT_RE.search(text) or any(n >= thr for n in _numbers(text)):
        return ["refund timeline given, but the message names an amount that may be Rs 1,00,000 or more (KB-07)"]
    return []


def check_language(reply: str, language: str) -> list[str]:
    body = reply.replace("Razorpay Support", "")
    got = detect_language(body)
    return [] if got == language else [f"reply language {got} does not match ticket language {language}"]


# ------------------------------------------------------------------ reply style (config: reply_style)

def _style() -> dict:
    return load_config()["reply_style"]


def _body(reply: str) -> str:
    """The reply without its first line (greeting) and the sign-off."""
    lines = reply.strip().splitlines()
    text = "\n".join(lines[1:]) if len(lines) > 1 else reply
    return text.replace(_style()["signoff"], "").strip()


def check_greeting(reply: str, greeting: str | None) -> list[str]:
    if not greeting:
        return []
    first = reply.strip().splitlines()[0].strip() if reply.strip() else ""
    return [] if first == greeting else [f"first line must be the greeting '{greeting}'"]


def check_signoff(reply: str) -> list[str]:
    return [] if reply.strip().endswith(_style()["signoff"]) else [f"must end with '{_style()['signoff']}'"]


def check_length(reply: str) -> list[str]:
    n = len(_body(reply).split())
    return [] if n <= _style()["max_words"] else [f"body is {n} words; limit is {_style()['max_words']}"]


def check_commitments(reply: str) -> list[str]:
    low = reply.lower()
    return [f"follow-up promise '{p}'" for p in _style()["commitment_phrases"] if p in low]


def check_voice(reply: str, language: str) -> list[str]:
    if language != "English":
        return []
    body = _body(reply)
    return [f"first-person singular ({p}); use 'we'" for p in _style()["first_person_en"] if re.search(p, body)]


def check_exclamation(reply: str) -> list[str]:
    return ["exclamation mark; keep the tone plain and professional"] if _style()["no_exclamation"] and "!" in reply else []


def check_empathy_scope(reply: str, tone: str | None) -> list[str]:
    """Empathy wording only for frustrated or angry merchants."""
    if tone in (None, "frustrated", "angry"):
        return []
    low = _body(reply).lower()
    return [f"empathy wording '{m}' for a calm merchant" for m in _style()["empathy_markers"] if m in low]


def check_keep(reply: str, keep: list[str]) -> list[str]:
    return [f"slot value '{k}' was changed or dropped" for k in keep if k not in reply]


def run_all(reply: str, *, message: str, merchant: dict | None, action: str, sub_case: str,
            kb_ids: list[str], missing_fields: list[str], language: str, send_mode: str,
            keep: list[str] | None = None, tone: str | None = None,
            greeting: str | None = None) -> GuardrailResult:
    checks = {
        "dates": check_dates(reply, merchant),
        "durations": check_durations(reply, kb_ids, action),
        "numbers": check_numbers(reply, message, merchant, kb_ids),
        "promises": check_promises(reply),
        "apology": check_apology(reply),
        "refund_timeline": check_refund_timeline(reply, message, sub_case),
        "internal_reasons": check_internal_reasons(reply, merchant, sub_case),
        "threat": check_threat(reply, sub_case, send_mode),
        "ask_info_fields": check_ask_info(reply, action, missing_fields),
        "language": check_language(reply, language),
        "slot_values": check_keep(reply, keep or []),
        # reply style (config reply_style)
        "greeting": check_greeting(reply, greeting),
        "signoff": check_signoff(reply),
        "length": check_length(reply),
        "commitments": check_commitments(reply),
        "voice": check_voice(reply, language),
        "exclamation": check_exclamation(reply),
        "empathy_scope": check_empathy_scope(reply, tone),
    }
    failures = [f for v in checks.values() for f in v]
    return GuardrailResult(passed=not failures, failures=failures,
                           checks={k: ("PASS" if not v else "FAIL: " + "; ".join(v)) for k, v in checks.items()})
