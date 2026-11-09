"""Rules engine: the KB as a decision table.

Rules are applied in priority order; the first match decides the action.
Every decision carries a plain-words trace and the KB article(s) it rests on.
No ticket or merchant IDs appear here; thresholds and lists live in config/rules.yaml.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

from .config import load_config, team_name
from .extract import Extraction
from .lookup import business_days_elapsed, inr

RISK_ORDER = ["Low", "Medium", "High", "Critical"]


@dataclass
class Decision:
    category: str
    action: str                       # auto_resolve / ask_info / escalate
    sub_case: str
    risk_level: str
    escalation_team: str = ""
    secondary_team: str = ""
    kb_ids: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    churn_signal: bool = False
    threat_type: str = "none"
    trace: list[str] = field(default_factory=list)
    slots: dict = field(default_factory=dict)   # values the reply template may use

    def to_dict(self) -> dict:
        return asdict(self)


def _any(patterns: list[str], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


def _risk(sub_case: str) -> str:
    return load_config()["risk"][sub_case]


def _bump(level: str) -> str:
    """Raise one level, capped at High (Critical only comes from threats)."""
    if level == "Critical":
        return level
    i = RISK_ORDER.index(level)
    return RISK_ORDER[min(i + 1, 2)]


def _mk(category, action, sub_case, kb, trace, team="", secondary="", missing=None, slots=None, risk=None):
    return Decision(category=category, action=action, sub_case=sub_case,
                    risk_level=risk or _risk(sub_case),
                    escalation_team=team_name(team) if team else "",
                    secondary_team=team_name(secondary) if secondary else "",
                    kb_ids=list(kb), missing_fields=list(missing or []),
                    trace=list(trace), slots=dict(slots or {}))


# ------------------------------------------------------------------ rule 1: threats

def rule_threat(ex: Extraction, message: str) -> Decision | None:
    if ex.threat_type == "none":
        return None
    cfg = load_config()["threats"]
    t = next(t for t in cfg["types"] if t["name"] == ex.threat_type)
    secondary = ""
    if t.get("secondary_if_keywords") and any(
            re.search(rf"\b{re.escape(k)}\b", message, re.I) for k in t["secondary_if_keywords"]):
        secondary = t["secondary_team"]
    # Decision D3: a pure threat is Legal / Security; a legal threat on a clear topic keeps the topic.
    category = "Legal / Security" if t["pure_threat"] or not ex.intent_category else ex.intent_category
    why = (f"keywords {ex.threat_keywords}" if ex.threat_keywords else "LLM threat flag")
    trace = [f"Rule 1 (KB-15): threat detected ({ex.threat_type}, {why}).",
             f"Escalate immediately to {team_name(t['team'])}"
             + (f" with {team_name(secondary)} as secondary (police/authorities mentioned)." if secondary else "."),
             "Never auto-replied: holding draft only, for the escalation team to approve."]
    d = _mk(category, "escalate", "threat", ["KB-15"], trace, team=t["team"], secondary=secondary)
    d.threat_type = ex.threat_type
    return d


# ------------------------------------------------------------------ topic rules

def rule_settlement(m: dict, trace: list[str]) -> Decision:
    status, reason = m.get("settlement_status"), m.get("hold_reason")
    slots = {"last_settlement_date": m.get("last_settlement_date"),
             "last_settlement_amount": inr(m.get("last_settlement_amount_inr")),
             "expected_settlement_date": m.get("expected_settlement_date")}
    cat = "Settlement"
    if status == "Settled":
        return _mk(cat, "auto_resolve", "settlement_settled", ["KB-01"],
                   trace + [f"Rule 4 (KB-01): merchant status Settled; share last settlement "
                            f"{slots['last_settlement_amount']} on {slots['last_settlement_date']} from the system."],
                   slots=slots)
    if status == "Delayed":
        return _mk(cat, "auto_resolve", "settlement_delayed", ["KB-02"],
                   trace + [f"Rule 4 (KB-02): status Delayed (bank-side); share expected date "
                            f"{slots['expected_settlement_date']} exactly as in the system."], slots=slots)
    if status == "On hold":
        if reason in ("Risk review", "Chargeback reserve"):
            return _mk(cat, "escalate", "settlement_hold_escalate", ["KB-03"],
                       trace + [f"Rule 4 (KB-03): on hold ({reason}). CS cannot release or shorten holds; "
                                "escalate to Risk Ops. Reason must not be shared."], team="risk_ops", slots=slots)
        if reason == "KYC pending":
            return _mk(cat, "auto_resolve", "settlement_kyc_pending", ["KB-04", "KB-10"],
                       trace + ["Rule 4 (KB-04): on hold for pending KYC; guide to Dashboard > Account > KYC."],
                       slots=slots)
        if reason == "Bank account mismatch":
            return _mk(cat, "auto_resolve", "settlement_bank_mismatch", ["KB-05"],
                       trace + ["Rule 4 (KB-05): on hold for bank account name mismatch; guide to re-add the "
                                "account (penny-drop within 24 hours)."], slots=slots)
    return _mk(cat, "escalate", "settlement_hold_escalate", ["KB-03"],
               trace + [f"Rule 4: settlement status '{status}' / reason '{reason}' not covered by the KB; "
                        "escalate to Risk Ops."], team="risk_ops", slots=slots)


def rule_payment(ex: Extraction, m: dict, message: str, trace: list[str]) -> Decision:
    cfg = load_config()
    rate = m.get("payment_success_rate_7d_pct")
    thr = cfg["thresholds"]["success_rate_degradation_pct"]
    cat = "Payment Failure"
    if rate is not None and rate < thr:
        return _mk(cat, "escalate", "payment_degradation_escalate", ["KB-06"],
                   trace + [f"Rule 5 (KB-06): 7-day success rate {rate}% is below {thr}%; possible "
                            "degradation. Escalate to Payments Ops; do not blame customers."], team="payments_ops")
    if ex.intent == "deducted_order_failed" and not ex.payment_id:
        return _mk(cat, "ask_info", "deducted_ask_payment_id", ["KB-06", "KB-16"],
                   trace + [f"Rule 5 (KB-06, KB-16): success rate {rate}% is healthy. 'Money deducted, order "
                            "failed' with no payment ID: ask for it (decision D2); mention auto-reversal."],
                   missing=["payment_id"])
    if ex.intent == "deducted_order_failed":
        return _mk(cat, "auto_resolve", "payment_failing_auto", ["KB-06"],
                   trace + [f"Rule 5 (KB-06): success rate {rate}% healthy; deducted amounts auto-reverse."])
    sub = "payment_failing_sales_stopped" if _any(cfg["sales_stopped_patterns"], message) else "payment_failing_auto"
    d = _mk(cat, "auto_resolve", sub, ["KB-06"],
            trace + [f"Rule 5 (KB-06): success rate {rate}% is at or above {thr}%; share KB-06 advice "
                     "(retry, other method, auto-reversal)."])
    if sub == "payment_failing_sales_stopped":
        d.trace.append("Merchant says sales have stopped: risk Medium.")
    return d


def rule_refund(ex: Extraction, created: datetime, trace: list[str]) -> Decision:
    cfg = load_config()["thresholds"]
    cat = "Refund"
    amount = ex.amount_inr
    slots = {"amount": inr(amount) if amount else "", "payment_id": ex.payment_id or ""}
    if amount is not None and amount >= cfg["refund_manual_approval_inr"]:
        return _mk(cat, "escalate", "refund_large_escalate", ["KB-07"],
                   trace + [f"Rule 6 (KB-07): refund {inr(amount)} is at or above "
                            f"{inr(cfg['refund_manual_approval_inr'])}; Refund Ops approves manually. "
                            "No timeline may be promised."], team="refund_ops", slots=slots)
    if not ex.payment_id:
        return _mk(cat, "ask_info", "refund_ask_payment_id", ["KB-07", "KB-16"],
                   trace + ["Rule 6 (KB-16): refund query without a payment ID; ask for it first."],
                   missing=["payment_id"], slots=slots)
    if ex.days_ago is not None:
        start = (created - timedelta(days=ex.days_ago)).date()
        bd = business_days_elapsed(start, created.date())
        slots["business_days_elapsed"] = bd
        if bd > cfg["refund_window_business_days"]:
            return _mk(cat, "escalate", "refund_overdue_escalate", ["KB-07"],
                       trace + [f"Rule 6 (KB-07, decision D1): initiated {ex.days_ago} calendar days before the "
                                f"ticket = {bd} business days, past the {cfg['refund_window_business_days']}-day "
                                "window. Escalate to Refund Ops to check status."], team="refund_ops", slots=slots)
        trace = trace + [f"Rule 6 (KB-07, decision D1): {ex.days_ago} calendar days = {bd} business days, "
                         "within the 5-7 business day window."]
    else:
        trace = trace + ["Rule 6 (KB-07): refund age not stated; share the standard window."]
    return _mk(cat, "auto_resolve", "refund_in_window", ["KB-07"],
               trace + ["Share 5-7 business days and ARN after 3 days. Never invent an ARN."], slots=slots)


def rule_chargeback(ex: Extraction, m: dict, trace: list[str]) -> Decision:
    cat = "Chargeback"
    open_cb = m.get("open_chargebacks")
    if ex.intent == "dispute_deduction":
        if not open_cb:
            return _mk(cat, "ask_info", "dispute_ask_reference", ["KB-08", "KB-16"],
                       trace + [f"Rule 7 (KB-08, decision D6): merchant reports a dispute debit but the system "
                                f"shows {open_cb or 0} open chargebacks. Confirm neither side; ask for the debit "
                                "reference."], missing=["debit_reference"])
        return _mk(cat, "auto_resolve", "dispute_with_open_chargeback", ["KB-08"],
                   trace + [f"Rule 7 (KB-08): {open_cb} open chargeback(s) in the system; point to Dashboard > "
                            "Disputes and the 7-day evidence window."], slots={"open_chargebacks": open_cb})
    if ex.intent == "chargeback_prevent":
        return _mk(cat, "auto_resolve", "chargeback_prevent", ["KB-08"],
                   trace + ["Rule 7 (KB-08): disputes cannot be blocked in advance; explain evidence process."])
    return _mk(cat, "auto_resolve", "chargeback_notice", ["KB-08"],
               trace + ["Rule 7 (KB-08): explain Disputes notice, 7 calendar days for evidence, missed deadline "
                        "loses the dispute."])


def rule_kyc(ex: Extraction, m: dict, trace: list[str]) -> Decision:
    cat = "KYC"
    if ex.intent == "kyc_reverification_check":
        status = m.get("kyc_status")
        if status == "Verified":
            return _mk(cat, "escalate", "kyc_phishing_escalate", ["KB-10"],
                       trace + ["Rule 8 (KB-10, decision D5): merchant KYC is already Verified, so a "
                                "re-verification message is suspicious. Warn the merchant (genuine requests "
                                "come only from the Dashboard or @example.com) and escalate to Security."],
                       team="security")
        return _mk(cat, "auto_resolve", "kyc_reverification_guide", ["KB-10"],
                   trace + [f"Rule 8 (KB-10): system KYC status is '{status}'; guide to the Dashboard and "
                            "warn to act only via Dashboard or @example.com emails."], slots={"kyc_status": status})
    return _mk(cat, "auto_resolve", "kyc_documents", ["KB-10"],
               trace + ["Rule 8 (KB-10): share the required KYC document list."])


def rule_fees(ex: Extraction, m: dict, message: str, trace: list[str]) -> Decision:
    cfg = load_config()
    cat = "Fees & Invoices"
    if ex.intent == "invoice_request":
        if (m.get("gst_invoice_available") or "").lower() == "no":
            return _mk(cat, "escalate", "invoice_unavailable_escalate", ["KB-09"],
                       trace + ["Rule 9 (KB-09, decision D7): the system shows no GST invoice available for this "
                                "merchant, so pointing to the Dashboard would be wrong. Escalate to the Account "
                                "Manager."], team="account_manager")
        return _mk(cat, "auto_resolve", "invoice_available", ["KB-09"],
                   trace + ["Rule 9 (KB-09): invoice available; generated by the 5th under Dashboard > Reports > "
                            "Invoices."])
    d = _mk(cat, "escalate", "fee_commercial_escalate", ["KB-09"],
            trace + [f"Rule 9 (KB-09): {ex.intent.replace('_', ' ')} is handled only by the Account Manager. "
                     "No promise of waiver, refund or rate change."], team="account_manager")
    if _any(cfg["churn_patterns"], message):
        d.churn_signal = True
        d.trace.append("Competitor or leaving language: churn signal set.")
    return d


def rule_api(ex: Extraction, message: str, trace: list[str]) -> Decision:
    cfg = load_config()
    cat = "API & Integration"
    fixed = {"api_signature": ("KB-12", "SIGNATURE_MISMATCH fix"),
             "api_amount_mismatch": ("KB-12", "amounts in paise"),
             "api_auth_failed": ("KB-14", "test keys on a live site"),
             "api_webhook": ("KB-13", "webhook checklist")}
    if ex.intent in fixed:
        kb, what = fixed[ex.intent]
        return _mk(cat, "auto_resolve", ex.intent, [kb],
                   trace + [f"Rule 10 ({kb}): known API issue; share the exact KB fix ({what}). "
                            "Not a payment failure, so success rate is not used."])
    prod = _any(cfg["api_production_patterns"], message)
    sub = "api_no_kb_escalate_production" if prod else "api_no_kb_escalate"
    return _mk(cat, "escalate", sub, [],
               trace + ["Rule 10: no KB article covers this API issue; escalate to Tech Support, never guess."
                        + (" Production impact stated: risk High." if prod else "")], team="tech_support")


def rule_account(ex: Extraction, message: str, trace: list[str]) -> Decision:
    cat = "Account Management"
    if ex.intent == "account_closure":
        d = _mk(cat, "escalate", "account_closure_escalate", ["KB-17"],
                trace + ["Rule 11 (KB-17): closure goes through the Account Manager and Risk Ops after pending "
                         "settlements, refunds and disputes clear."], team="account_manager", secondary="risk_ops")
        d.churn_signal = True
        return d
    if ex.intent == "change_legal_name":
        return _mk(cat, "auto_resolve", "account_change_legal_name", ["KB-11"],
                   trace + ["Rule 11 (KB-11): a legal entity name or business type change needs a fresh "
                            "application; it cannot be edited."])
    return _mk(cat, "auto_resolve", "account_change_contact", ["KB-11"],
               trace + ["Rule 11 (KB-11): email and mobile change in Settings with OTP verification."])


# ------------------------------------------------------------------ main

def decide(ex: Extraction, merchant: dict | None, message: str, created: datetime) -> Decision:
    trace: list[str] = []
    d = rule_threat(ex, message)
    if d is None:
        d = _decide_topic(ex, merchant, message, created, trace)
    _apply_tone(d, ex)
    return d


def _vague_fields(category: str) -> list[str]:
    return ["payment_id", "details"] if category == "Payment Failure" else ["details"]


def _decide_topic(ex: Extraction, merchant: dict | None, message: str, created: datetime,
                  trace: list[str]) -> Decision:
    category = ex.category if ex.category != "Legal / Security" else "Unclear"

    # Rule 2: missing merchant ID (KB-16) comes before anything else.
    if merchant is None:
        missing = ["merchant_id"] + (_vague_fields(category) if ex.is_vague else [])
        if category == "Refund" and not ex.payment_id:
            missing.append("payment_id")
        return _mk(category, "ask_info", "missing_merchant_id", ["KB-16"],
                   ["Rule 2 (KB-16): no merchant ID in the ticket or message; ask for it before anything else."]
                   + (["Message is also too vague; ask what the issue is."] if ex.is_vague else []),
                   missing=missing)

    # Rule 3: too vague to act on. Exception: a clear settlement topic the record answers.
    if ex.is_vague:
        if category == "Settlement":
            trace.append("Rule 3: message is vague, but the topic (settlement) is clear and the merchant "
                         "record answers it; answer from the data instead of asking.")
        else:
            return _mk(category, "ask_info", "vague_ask_info", ["KB-16"],
                       [f"Rule 3 (KB-16): message too vague to act on (topic: {category}); ask for specifics."],
                       missing=_vague_fields(category))

    intent = ex.intent
    if category == "Settlement":
        return rule_settlement(merchant, trace)
    if category == "Payment Failure":
        return rule_payment(ex, merchant, message, trace)
    if category == "Refund":
        return rule_refund(ex, created, trace)
    if category == "Chargeback":
        return rule_chargeback(ex, merchant, trace)
    if category == "KYC":
        return rule_kyc(ex, merchant, trace)
    if category == "Fees & Invoices" and intent:
        return rule_fees(ex, merchant, message, trace)
    if category == "API & Integration":
        return rule_api(ex, message, trace)
    if category == "Account Management" and intent:
        return rule_account(ex, message, trace)

    # The LLM named a category but no KB rule matched the request.
    fb = load_config()["fallback_team_by_category"].get(category)
    if fb:
        return _mk(category, "escalate", "no_rule_escalate", [],
                   [f"No KB rule matched this {category} request; escalate to {team_name(fb)} rather than guess."],
                   team=fb)
    return _mk("Unclear", "ask_info", "vague_ask_info", ["KB-16"],
               ["Rule 3 (KB-16): topic unclear; ask the merchant for specifics."], missing=["details"])


def _apply_tone(d: Decision, ex: Extraction) -> None:
    """Section 8.5: angry or urgent raises risk one level (max High). Tone never changes the action."""
    if d.risk_level == "Critical":
        return
    if ex.tone == "angry" or ex.urgent:
        old = d.risk_level
        d.risk_level = _bump(old)
        if d.risk_level != old:
            d.trace.append(f"Tone {ex.tone}{' + urgent' if ex.urgent else ''}: risk raised {old} -> {d.risk_level}.")
