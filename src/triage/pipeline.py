"""End-to-end triage: extract -> threats -> lookup -> rules -> draft -> guardrails -> send mode.

Run:  python -m triage.pipeline                (uses LLM caches; offline reader if no key and no cache)
      python -m triage.pipeline --refresh-llm  (re-calls the LLM for every ticket)
      python -m triage.pipeline --offline      (never calls or reads the LLM; keyword reader + templates)
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd

from . import draft, extract as ext_mod, guardrails, review
from .config import OUTPUTS, load_config
from .extract import extract
from .llm import llm_available, load_prompt
from .load import data_hash, load_tickets
from .lookup import get_merchant, resolve_merchant_id
from .rules import decide

BRIEF_COLUMNS = ["ticket_id", "category", "action", "escalation_team", "risk_level", "drafted_reply"]
EXTRA_COLUMNS = ["secondary_team", "sub_case", "kb_ids", "language", "tone", "threat_type", "missing_fields",
                 "send_mode", "guardrail_status", "churn_signal", "decision_trace"]
CONTEXT_COLUMNS = ["merchant_id", "channel", "created_at", "merchant_message", "intent", "urgent",
                   "threat_keywords", "extraction_source", "reply_source", "guardrail_failures",
                   "template_reply", "extraction_notes", "summary", "payment_id", "amount_inr"]


@dataclass
class TicketResult:
    row: dict
    guard_log: list[dict]


def offline_hold(extraction) -> bool:
    """True when there is no LLM reading, so a threat worded in a new way could be missed (config switch)."""
    return extraction.source == "offline" and load_config()["llm"].get("offline_blocks_auto_send", True)


def send_mode_for(decision, extraction, guard_passed: bool, apply_offline_hold: bool = True) -> str:
    """Section 8.1. Threats never auto-send; escalations and upset merchants get an agent's eyes.
    Without an LLM reading nothing auto-sends either."""
    if decision.sub_case == "threat" or decision.threat_type != "none":
        return "do_not_send"
    if not guard_passed:
        return "do_not_send"
    if decision.action == "escalate" or extraction.tone in ("frustrated", "angry"):
        return "agent_review"
    if decision.risk_level in ("High", "Critical"):
        return "agent_review"
    if apply_offline_hold and offline_hold(extraction):
        return "agent_review"
    return "auto_send"


def triage_ticket(ticket_id: str, message: str, merchant_id: str | None, created: datetime,
                  channel: str = "", created_at: str = "", refresh: bool = False,
                  offline: bool = False) -> TicketResult:
    ex = extract(message, refresh=refresh, offline=offline)
    mid, note = resolve_merchant_id(merchant_id, ex.merchant_id_in_message)
    if note:
        ex.notes.append(note)
    merchant = get_merchant(mid)
    if mid and merchant is None:
        ex.notes.append(f"Merchant {mid} not found in the merchant table; treated as missing")
    d = decide(ex, merchant, message, created)

    parts = draft.template_parts(d, ex, merchant)
    tpl_reply, keep = draft.assemble(parts, with_ack=True), parts["keep"]
    polish_in = draft.assemble(parts, with_ack=False)   # the model writes its own empathy line from the hint
    provisional_mode = "do_not_send" if d.sub_case == "threat" else "auto_send"
    guard_log = []

    def check(reply: str, attempt: int, source: str):
        g = guardrails.run_all(reply, message=message, merchant=merchant, action=d.action, sub_case=d.sub_case,
                               kb_ids=d.kb_ids, missing_fields=d.missing_fields, language=ex.language,
                               send_mode=provisional_mode, keep=keep, tone=ex.tone, greeting=parts["greeting"])
        guard_log.append({"ticket_id": ticket_id, "attempt": attempt, "reply_source": source,
                          "passed": g.passed, **g.checks})
        return g

    reply, source = tpl_reply, "template"
    if d.sub_case == "threat":
        # Threat holding replies use the fixed, Legal-safe template word for word. The polisher was adding
        # apologies for angry tone, which Legal could read as admitting fault (KB-15).
        pass
    else:
        try:
            reply, source = draft.polish(polish_in, keep, ex.language, ex.tone, refresh=refresh, offline=offline,
                                         ack_hint=parts["ack"], fallback=tpl_reply)
        except Exception as e:
            ex.notes.append(f"Polisher failed, template used ({type(e).__name__})")
    g = check(reply, 1, source)
    status = "PASS"
    if not g.passed:
        # Regenerate once with the failure reason; offline, fall back to the template text.
        retry, rsource = tpl_reply, "template"
        if source in ("llm", "cache"):
            try:
                retry, rsource = draft.polish(polish_in, keep, ex.language, ex.tone, feedback="; ".join(g.failures),
                                              refresh=refresh, offline=offline, ack_hint=parts["ack"],
                                              fallback=tpl_reply)
            except Exception as e:
                ex.notes.append(f"Polisher retry failed ({type(e).__name__})")
        g2 = check(retry, 2, rsource)
        if g2.passed:
            reply, source, status, g = retry, rsource, "PASS_AFTER_RETRY", g2
        else:
            reply, source, status, g = retry, rsource, "FAIL_NEEDS_HUMAN", g2

    mode = send_mode_for(d, ex, g.passed)
    if mode == "agent_review" and offline_hold(ex) and send_mode_for(d, ex, g.passed, apply_offline_hold=False) \
            == "auto_send":
        ex.notes.append("No LLM reading (keyword reader only): held for agent review instead of auto-send")
    row = {
        "ticket_id": ticket_id,
        "category": d.category,
        "action": d.action,
        "escalation_team": d.escalation_team,
        "risk_level": d.risk_level,
        "drafted_reply": reply,
        "secondary_team": d.secondary_team,
        "sub_case": d.sub_case,
        "kb_ids": ", ".join(d.kb_ids),
        "language": ex.language,
        "tone": ex.tone,
        "threat_type": d.threat_type,
        "missing_fields": ", ".join(d.missing_fields),
        "send_mode": mode,
        "guardrail_status": status,
        "churn_signal": d.churn_signal,
        "decision_trace": " ".join(d.trace),
        "merchant_id": mid or "",
        "channel": channel,
        "created_at": created_at,
        "merchant_message": message,
        "intent": ex.intent or "",
        "urgent": ex.urgent,
        "threat_keywords": ", ".join(ex.threat_keywords),
        "extraction_source": ex.source,
        "reply_source": source,
        "guardrail_failures": "; ".join(g.failures),
        "template_reply": tpl_reply,
        "extraction_notes": "; ".join(ex.notes),
        "summary": ex.summary or "",
        "payment_id": ex.payment_id or "",
        "amount_inr": "" if ex.amount_inr is None else (int(ex.amount_inr) if float(ex.amount_inr).is_integer()
                                                        else ex.amount_inr),
    }
    return TicketResult(row=row, guard_log=guard_log)


def apply_human_review(df: pd.DataFrame) -> None:
    """A draft Vasudev rejected (status 'open' in docs/replies_rejected.md) is never sent."""
    for tid, reason in review.open_rejections().items():
        mask = df.ticket_id == tid
        if mask.any():
            df.loc[mask, "send_mode"] = "do_not_send"
            df.loc[mask, "extraction_notes"] = df.loc[mask, "extraction_notes"].map(
                lambda n: "; ".join(x for x in (n, f"Rejected in human review: {reason}") if x))


def not_sent_table(df: pd.DataFrame) -> pd.DataFrame:
    """Every reply not sent, and why: automatic blocks (threats, guardrail failures) plus human rejections,
    including rejections already fixed, which stay listed as a record."""
    cols = ["ticket_id", "category", "action", "escalation_team", "source", "status", "reason_not_sent",
            "rejected_draft", "current_reply"]
    auto = df[(df.send_mode == "do_not_send") & ~df.ticket_id.isin(review.open_rejections())].copy()
    auto["source"] = "automatic"
    auto["status"] = "blocked"
    auto["reason_not_sent"] = auto.apply(
        lambda r: ("Threat ticket (KB-15): never auto-replied; holding draft for the escalation team."
                   if r.threat_type != "none" else "Guardrail failed twice: " + r.guardrail_failures), axis=1)
    auto["rejected_draft"] = ""
    auto["current_reply"] = auto.drafted_reply
    rows = [auto]
    by_id = df.set_index("ticket_id")
    for rej in review.load_rejections():
        for tid in rej.tickets:
            if tid not in by_id.index:
                continue
            r = by_id.loc[tid]
            rows.append(pd.DataFrame([{
                "ticket_id": tid, "category": r.category, "action": r.action,
                "escalation_team": r.escalation_team, "source": "human review",
                "status": "blocked" if rej.status == "open" else "fixed",
                "reason_not_sent": rej.reason, "rejected_draft": rej.excerpt, "current_reply": r.drafted_reply}]))
    return pd.concat(rows, ignore_index=True)[cols]


def run(refresh: bool = False, offline: bool = False, workers: int = 8) -> pd.DataFrame:
    tickets = load_tickets()
    use_threads = llm_available() and not offline

    def one(r):
        return triage_ticket(r.ticket_id, r.merchant_message, r.merchant_id, r.created_dt.to_pydatetime(),
                             channel=r.channel, created_at=r.created_at, refresh=refresh, offline=offline)

    rows = list(tickets.itertuples())
    if use_threads:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(one, rows))
    else:
        results = [one(r) for r in rows]
    if not offline:
        ext_mod.save_cache()
        draft.save_cache()

    df = pd.DataFrame([r.row for r in results])[BRIEF_COLUMNS + EXTRA_COLUMNS + CONTEXT_COLUMNS]
    apply_human_review(df)
    guard = pd.DataFrame([g for r in results for g in r.guard_log])
    write_outputs(df, guard, tickets, offline=offline)
    return df


def write_outputs(df: pd.DataFrame, guard: pd.DataFrame, tickets: pd.DataFrame, offline: bool) -> None:
    from . import kb_insights, spikes

    OUTPUTS.mkdir(exist_ok=True)
    df.to_csv(OUTPUTS / "triage_results.csv", index=False, encoding="utf-8")
    guard.to_csv(OUTPUTS / "guardrail_log.csv", index=False, encoding="utf-8")
    df[df.action == "escalate"][BRIEF_COLUMNS + ["secondary_team", "threat_type", "send_mode", "decision_trace"]] \
        .sort_values(["escalation_team", "ticket_id"]).to_csv(OUTPUTS / "escalations.csv", index=False)

    not_sent_table(df).to_csv(OUTPUTS / "replies_not_sent.csv", index=False, encoding="utf-8")

    spikes.write(df)
    kb_insights.write(df)
    write_safety_checks(df)

    with pd.ExcelWriter(OUTPUTS / "triage_results.xlsx") as xw:
        df[BRIEF_COLUMNS + EXTRA_COLUMNS].to_excel(xw, sheet_name="triage_results", index=False)
        df.to_excel(xw, sheet_name="full_detail", index=False)

    cfg = load_config()
    meta = {
        "run_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config_version": cfg["version"],
        "config_frozen": cfg["frozen"],
        "model": cfg["llm"]["model"],
        "prompt_versions": {"extractor": load_prompt("extractor")[0], "reply_polisher": load_prompt("reply_polisher")[0]},
        "mode": "offline" if offline else ("llm_or_cache" if llm_available() else "cache_or_offline"),
        "extraction_sources": df.extraction_source.value_counts().to_dict(),
        "reply_sources": df.reply_source.value_counts().to_dict(),
        "data_file_sha256": data_hash(),
        "n_tickets": int(len(df)),
    }
    (OUTPUTS / "run_metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def write_safety_checks(df: pd.DataFrame) -> dict:
    """Critical-error self-checks that need no gold labels."""
    threats = df[df.threat_type != "none"]
    sent = df[df.send_mode == "auto_send"]
    checks = {
        "threat_tickets": int(len(threats)),
        "threats_not_escalated": int((threats.action != "escalate").sum()),
        "threats_not_do_not_send": int((threats.send_mode != "do_not_send").sum()),
        "auto_send_with_guardrail_failure": int((sent.guardrail_status == "FAIL_NEEDS_HUMAN").sum()),
        "escalations_auto_sent": int(((df.action == "escalate") & (df.send_mode == "auto_send")).sum()),
        "guardrail_fail_needs_human": int((df.guardrail_status == "FAIL_NEEDS_HUMAN").sum()),
        "guardrail_pass_after_retry": int((df.guardrail_status == "PASS_AFTER_RETRY").sum()),
    }
    (OUTPUTS / "safety_checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    return checks


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh-llm", action="store_true", help="re-call the LLM instead of using caches")
    ap.add_argument("--offline", action="store_true", help="keyword reader and templates only")
    args = ap.parse_args()
    if args.refresh_llm and not llm_available():
        raise SystemExit("--refresh-llm needs ANTHROPIC_API_KEY in .env or the environment.")
    df = run(refresh=args.refresh_llm, offline=args.offline)
    print(f"Triaged {len(df)} tickets -> {OUTPUTS / 'triage_results.csv'}")
    print(df.action.value_counts().to_string())
    print("send_mode:", df.send_mode.value_counts().to_dict())
    print("guardrails:", df.guardrail_status.value_counts().to_dict())
    print("sources:", df.extraction_source.value_counts().to_dict(), df.reply_source.value_counts().to_dict())


if __name__ == "__main__":
    main()
