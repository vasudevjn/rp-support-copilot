"""Ticket Detail building blocks, shared by the Workspace page and Try It.

Two columns: left is the merchant's message and the merchant facts that matter; right is what to do and why,
then the drafted reply. Each block takes one triage row (a dict with the columns of outputs/triage_results.csv)
and the guardrail log rows for that ticket. Nothing here decides anything: it shows what the pipeline decided.
"""
from __future__ import annotations

import streamlit as st

from common import ACTION_LABELS, MODE_LABELS, chip, dl, esc, risk_pill, show
from triage.config import load_config
from triage.load import load_kb
from triage.lookup import get_merchant, inr

PAYMENT_SUB_CASES = {"payment_degradation_escalate", "payment_failing_auto", "payment_failing_sales_stopped",
                     "deducted_ask_payment_id"}
CHECK_NAMES = {"dates": "Dates", "durations": "Durations", "numbers": "Numbers", "promises": "Promise phrases",
               "apology": "No apology", "refund_timeline": "Refund timeline", "internal_reasons": "Internal reasons",
               "threat": "Threat rules", "ask_info_fields": "Ask-info fields", "language": "Language match",
               "slot_values": "Slot values kept", "greeting": "Greeting", "signoff": "Sign-off",
               "length": "Length", "commitments": "No follow-up promise", "voice": "We voice",
               "exclamation": "No exclamation", "empathy_scope": "Empathy only when upset"}


def is_threat(r: dict) -> bool:
    return r.get("threat_type", "none") not in ("none", "")


def action_sentence(r: dict) -> str:
    if r["action"] == "escalate":
        team = r["escalation_team"] + (f" + {r['secondary_team']}" if r.get("secondary_team") else "")
        return f"Escalate To {team}"
    if r["action"] == "ask_info":
        return "Ask The Merchant For Information"
    return "Auto-Resolve With The KB Answer"


def kb_ids(r: dict) -> list[str]:
    return [k.strip() for k in str(r.get("kb_ids", "")).split(",") if k.strip()]


def merchant_label(r: dict) -> str:
    m = get_merchant(r.get("merchant_id") or None)
    return m["business_name"] if m else "No merchant ID"


def threat_banner(r: dict) -> None:
    if is_threat(r):
        show('<div class="alert" role="alert"><b>Critical Threat. Sending Is Disabled.</b></div>')


def failed_checks(g: dict) -> list[str]:
    return [CHECK_NAMES.get(c, c) for c, v in g.items() if c in CHECK_NAMES and str(v).startswith("FAIL")]


# ------------------------------------------------------------------ left column

def message_card(r: dict) -> None:
    meta = " · ".join(x for x in [r.get("channel", ""), r.get("created_at", ""), r["language"]] if x)
    pairs = [("Tone", str(r["tone"]).title())]
    if r.get("payment_id"):
        pairs.append(("Payment ID", r["payment_id"]))
    if str(r.get("amount_inr", "")) not in ("", "None"):
        pairs.append(("Amount", inr(float(r["amount_inr"]))))
    show(f'<section class="card"><p class="lbl">Message</p><p class="msg">{esc(r["merchant_message"])}</p>'
         f'<p class="meta">{esc(meta)}</p>{dl(pairs)}</section>')


def merchant_card(r: dict, key: str) -> None:
    m = get_merchant(r.get("merchant_id") or None)
    if not m:
        show('<section class="card"><p class="lbl">Merchant</p><p style="margin:0;font-size:13px;color:#556070">'
             'No merchant ID on this ticket, so the reply asks for it first.</p></section>')
        return
    gauge = ""
    if r.get("sub_case") in PAYMENT_SUB_CASES:
        thr = load_config()["thresholds"]["success_rate_degradation_pct"]
        rate = float(m["payment_success_rate_7d_pct"])
        color = "#C2410C" if rate < thr else "#175C43"
        gauge = (f'<div style="display:flex;justify-content:space-between;font-size:13px"><b>7-day payment success rate</b>'
                 f'<b style="color:{color}">{rate:g}%</b></div>'
                 f'<div class="gauge" role="img" aria-label="Success rate {rate:g} percent, threshold {thr} percent">'
                 f'<div class="f" style="width:{rate}%;background:{color}"></div><div class="th" style="left:{thr}%"></div></div>'
                 f'<div style="position:relative;height:16px;font-size:12px;color:#556070"><span style="position:absolute;left:0">0%</span>'
                 f'<span style="position:absolute;left:{thr}%;transform:translateX(-50%);color:#101828;font-weight:600;'
                 f'white-space:nowrap">{thr}% threshold</span><span style="position:absolute;right:0">100%</span></div>')
    status = m["settlement_status"] + (f", {m['hold_reason']}" if m.get("hold_reason") else "")
    if m.get("expected_settlement_date"):
        status += f", expected {m['expected_settlement_date']}"
    pairs = [("Settlement", status), ("KYC", m["kyc_status"]),
             ("Last settlement", f"{m['last_settlement_date']}, {inr(m['last_settlement_amount_inr'])}")]
    show(f'<section class="card"><p class="lbl">Merchant · {esc(m["merchant_id"])}</p>{gauge}{dl(pairs)}</section>')
    if st.button(f"Open {m['merchant_id']}", key=f"m_{key}", icon=":material/storefront:"):
        merchant_dialog(m["merchant_id"])


# ------------------------------------------------------------------ right column

def recommendation_card(r: dict) -> None:
    show(f'<section class="card"><p class="lbl">Recommendation</p>'
         f'<div class="big">{esc(action_sentence(r))}</div>'
         f'<p class="meta">Risk {esc(r["risk_level"])} · {esc(MODE_LABELS.get(r["send_mode"], r["send_mode"]))}</p>'
         f'<p style="margin:0;font-size:14px;line-height:1.6;color:#344054"><b>Why:</b> {esc(r["decision_trace"])}</p>'
         f'</section>')
    kb = load_kb()
    ids = kb_ids(r)
    if ids:
        cols = st.columns(len(ids))
        for col, k in zip(cols, ids):
            if col.button(f"{k} · {kb.get(k, {}).get('topic', '')}", key=f"kb_{r['ticket_id']}_{k}",
                          icon=":material/menu_book:", use_container_width=True):
                kb_dialog(k)


def reply_card(r: dict, guard: list[dict], key: str) -> None:
    status = str(r.get("guardrail_status", ""))
    n = len([c for c in (guard[-1] if guard else {}) if c in CHECK_NAMES])
    if status == "PASS":
        line, color = f"Passed all {n} checks", "#175C43"
    elif status == "PASS_AFTER_RETRY":
        first = ", ".join(failed_checks(guard[0])) if guard else ""
        line, color = f"Passed after one retry (first draft failed: {first})", "#175C43"
    else:
        line, color = "Blocked: failed " + ", ".join(failed_checks(guard[-1]) if guard else []), "#B42318"
    show(f'<section class="card"><p class="lbl">Drafted Reply</p><p class="reply">{esc(r["drafted_reply"])}</p>'
         f'<p class="meta" style="color:{color};font-weight:600">{esc(line)}</p></section>')
    if st.button("Audit Trail", key=f"aud_{key}", icon=":material/history:"):
        audit_dialog(r, guard)


# ------------------------------------------------------------------ dialogs

@st.dialog("Knowledge Base Article", width="large")
def kb_dialog(k: str) -> None:
    a = load_kb().get(k, {})
    show(f'<p class="lbl">{esc(k)}</p><h3 style="margin:4px 0 8px;font-size:20px">{esc(a.get("topic", ""))}</h3>'
         f'<p style="font-size:15px;line-height:1.65;color:#1D2939">{esc(a.get("guidance", ""))}</p>'
         f'<p style="font-size:12px;color:#556070">The knowledge base is the rulebook. The copilot applies it and never overrides it.</p>')


@st.dialog("Merchant Record", width="large")
def merchant_dialog(mid: str) -> None:
    from common import results
    m = get_merchant(mid) or {}
    show(f'<h3 style="margin:0 0 12px;font-size:20px">{esc(m.get("business_name", mid))}</h3>'
         + dl([(k.replace("_", " ").capitalize(), "" if v is None else v) for k, v in m.items()]))
    df = results()
    t = df[df.merchant_id == mid]
    show('<p class="lbl" style="margin-top:16px">Tickets From This Merchant</p><div class="rows">' + "".join(
        f'<div class="row"><div class="m"><b>{esc(x.ticket_id)}</b> <span style="color:#344054">· {esc(x.category)}</span>'
        f'<small>{esc(x.created_at)}</small></div>{risk_pill(x.risk_level)}</div>' for x in t.itertuples()) + "</div>")


@st.dialog("Audit Trail", width="large")
def audit_dialog(r: dict, guard: list[dict]) -> None:
    src = "Claude reading (cached)" if r.get("extraction_source") in ("cache", "llm") else "offline keyword reader"
    kw = r.get("threat_keywords") or "none"
    attempts = "; ".join(f"attempt {g.get('attempt')}: {'PASS' if str(g.get('passed')) == 'True' else 'FAIL'}"
                         for g in guard) or "not logged"
    steps = [
        ("Extraction", f"{src}. Merchant ID {r.get('merchant_id') or 'missing'}, language {r['language']}, "
                       f"tone {r['tone']}, threat type {str(r.get('threat_type', 'none')).replace('_', ' ')}."),
        ("Threat check", f"Keywords matched: {kw}. Either the keyword list or the model flag is enough to escalate."),
        ("Merchant lookup", f"{r.get('merchant_id')} found." if get_merchant(r.get("merchant_id") or None)
         else "No merchant record (no ID on the ticket)."),
        ("Rule fired", f"{r['decision_trace']} KB: {r.get('kb_ids') or 'none'}."),
        ("Reply drafted", f"Template filled by code, reply source: {r.get('reply_source')}."),
        ("Guardrails", f"{r.get('guardrail_status')} ({attempts})."),
        ("Send mode", f"{MODE_LABELS.get(r['send_mode'], r['send_mode'])}. Action: {ACTION_LABELS[r['action']]}."),
    ]
    show('<ol class="steps">' + "".join(f'<li><span>{i}</span><div><b>{esc(t)}</b><p>{esc(d)}</p></div></li>'
                                        for i, (t, d) in enumerate(steps, 1)) + "</ol>")


# ------------------------------------------------------------------ page

def workspace(r: dict, guard: list[dict], key: str) -> None:
    """The two-column detail view for one ticket."""
    threat_banner(r)
    left, right = st.columns([1, 1.2], gap="medium")
    with left:
        message_card(r)
        merchant_card(r, key)
    with right:
        recommendation_card(r)
        reply_card(r, guard, key)


def header_pills(r: dict) -> str:
    return (f'<div style="display:flex;flex-wrap:wrap;align-items:center;gap:12px">'
            f'<h1 style="margin:0;font-family:\'Space Grotesk\',Inter,sans-serif;font-size:28px;font-weight:600">'
            f'{esc(r["ticket_id"])}</h1>{risk_pill(r["risk_level"]).replace("</span>", " risk</span>")}'
            f'{chip(r["category"])}'
            f'<span style="font-size:14px;color:#556070">{esc(merchant_label(r))}</span></div>')
