"""Measured results without a hand-labelled gold set.

Two kinds of evidence, both computed from outputs/triage_results.csv:
1. Spec cases: the expected outcomes Vasudev wrote in the spec (CLAUDE.md section 13) before the build,
   stored in eval/spec_cases.yaml. Each stated field is checked; fields the spec leaves open are not scored.
2. Whole-run safety checks over all 150 tickets (the brief's critical errors): threats escalated and never
   sent, escalation replies with no durations, no promise phrases, no guardrail failure sent, ask-info replies
   ask for what is missing, the threat keyword list hits no non-threat ticket.

This is not an accuracy estimate for all 150 tickets: the spec cases were picked to cover the risky paths,
not sampled at random. Reported as such.

Run:  python -m triage.evaluate
"""
from __future__ import annotations

import json
import re

import pandas as pd
import yaml

from .config import EVAL, OUTPUTS, load_config
from .extract import threat_keywords
from .load import load_tickets

DURATION_RE = re.compile(r"\d+\s*(?:-\s*\d+)?\s*(?:business |calendar )?(?:days?|hours?|din)\b", re.I)
FIELDS = ["category", "action", "team", "secondary_team", "risk", "send_mode", "kb", "reply_contains",
          "reply_excludes", "no_duration", "missing"]


def _as_list(v) -> list:
    return v if isinstance(v, list) else [v]


def check_case(case: dict, r: pd.Series) -> list[dict]:
    """Return one row per stated field: expected, actual, pass."""
    reply = str(r.drafted_reply)
    low = reply.lower()
    out = []

    def add(field, expected, actual, ok):
        out.append({"ticket_id": case["ticket"], "note": case.get("note", ""), "field": field,
                    "expected": expected, "actual": actual, "pass": bool(ok)})

    simple = {"category": "category", "action": "action", "team": "escalation_team",
              "secondary_team": "secondary_team", "risk": "risk_level", "send_mode": "send_mode"}
    for f, col in simple.items():
        if f in case:
            allowed = [str(x) for x in _as_list(case[f])]
            add(f, " or ".join(allowed), r[col], str(r[col]) in allowed)
    if "kb" in case:
        add("kb", f"includes {case['kb']}", r.kb_ids, case["kb"] in str(r.kb_ids))
    for s in _as_list(case.get("reply_contains", [])):
        add("reply_contains", s, "found" if s.lower() in low else "missing", s.lower() in low)
    for s in _as_list(case.get("reply_excludes", [])):
        hit = re.search(rf"\b{re.escape(s.lower())}\b", low)
        add("reply_excludes", f"no '{s}'", f"'{hit.group(0)}' found" if hit else "absent", not hit)
    if case.get("no_duration"):
        m = DURATION_RE.search(reply)
        add("no_duration", "no duration", m.group(0) if m else "none", not m)
    if "missing" in case:
        add("missing", f"asks for {case['missing']}", r.missing_fields, case["missing"] in str(r.missing_fields))
    return out


def safety_checks(df: pd.DataFrame) -> list[dict]:
    """Whole-run critical-error checks. Each row: check, failures (count), ticket_ids, target."""
    cfg = load_config()
    g = cfg["guardrails"]
    threats = df[df.threat_type != "none"]
    esc = df[df.action == "escalate"]
    sent = df[df.send_mode == "auto_send"]
    promise = re.compile("|".join(re.escape(p) for p in g["promise_phrases"]), re.I)
    tickets = load_tickets().set_index("ticket_id")
    kw_hits = {t for t, row in tickets.iterrows() if threat_keywords(row.merchant_message)}
    kw_false = sorted(kw_hits - set(threats.ticket_id))
    kw_missed = sorted(set(threats.ticket_id) - kw_hits)

    rows = [
        ("Threat not escalated", threats[threats.action != "escalate"].ticket_id),
        ("Threat not marked do_not_send", threats[threats.send_mode != "do_not_send"].ticket_id),
        ("Escalation set to auto_send", esc[esc.send_mode == "auto_send"].ticket_id),
        ("Escalation reply contains a duration", esc[esc.drafted_reply.str.contains(DURATION_RE)].ticket_id),
        ("Reply contains a promise phrase", df[df.drafted_reply.str.contains(promise)].ticket_id),
        ("Guardrail failure set to auto_send", sent[sent.guardrail_status == "FAIL_NEEDS_HUMAN"].ticket_id),
        ("Ask-info reply with no missing field listed",
         df[(df.action == "ask_info") & (df.missing_fields.str.strip() == "")].ticket_id),
        ("Threat keyword hit on a non-threat ticket", pd.Series(kw_false, dtype=str)),
        ("Reply style violation (greeting, voice, length, follow-up promise, empathy scope)",
         pd.Series(style_violations(df), dtype=str)),
    ]
    out = [{"check": c, "failures": int(len(ids)), "ticket_ids": " ".join(ids), "target": 0} for c, ids in rows]
    out.append({"check": "Threat tickets caught only by the LLM flag (not the keyword list)",
                "failures": len(kw_missed), "ticket_ids": " ".join(kw_missed), "target": "info"})
    return out


def style_violations(df: pd.DataFrame) -> list[str]:
    """Re-check every final reply against the reply_style spec, independently of the pipeline's own run."""
    from .draft import greeting_for
    from .guardrails import (check_commitments, check_empathy_scope, check_exclamation, check_greeting,
                             check_length, check_signoff, check_voice)
    from .lookup import get_merchant
    bad = []
    for r in df.itertuples():
        reply = str(r.drafted_reply)
        greeting = greeting_for(get_merchant(r.merchant_id or None), r.language)
        if (check_greeting(reply, greeting) or check_signoff(reply) or check_length(reply)
                or check_commitments(reply) or check_voice(reply, r.language) or check_exclamation(reply)
                or check_empathy_scope(reply, r.tone)):
            bad.append(r.ticket_id)
    return bad


def evaluate() -> dict:
    pred = pd.read_csv(OUTPUTS / "triage_results.csv", keep_default_na=False).set_index("ticket_id", drop=False)
    cases = yaml.safe_load((EVAL / "spec_cases.yaml").read_text(encoding="utf-8"))["cases"]

    checks = []
    for c in cases:
        if c["ticket"] not in pred.index:
            raise SystemExit(f"{c['ticket']} not in triage_results.csv")
        checks += check_case(c, pred.loc[c["ticket"]])
    chk = pd.DataFrame(checks)
    per_case = chk.groupby("ticket_id", sort=False).agg(note=("note", "first"), checks=("pass", "size"),
                                                         passed=("pass", "sum")).reset_index()
    per_case["all_pass"] = per_case.checks == per_case.passed
    safety = pd.DataFrame(safety_checks(pred.reset_index(drop=True)))

    def field_rate(fields):
        s = chk[chk.field.isin(fields)]
        return (int(s["pass"].sum()), int(len(s)))

    n = len(pred)
    res = {
        "config_version": load_config()["version"],
        "spec_cases": int(len(per_case)),
        "spec_cases_all_pass": int(per_case.all_pass.sum()),
        "spec_checks": int(len(chk)),
        "spec_checks_passed": int(chk["pass"].sum()),
        "action_checks_passed": "{}/{}".format(*field_rate(["action"])),
        "team_checks_passed": "{}/{}".format(*field_rate(["team", "secondary_team"])),
        "category_checks_passed": "{}/{}".format(*field_rate(["category"])),
        "risk_checks_passed": "{}/{}".format(*field_rate(["risk"])),
        "reply_checks_passed": "{}/{}".format(*field_rate(["reply_contains", "reply_excludes", "no_duration",
                                                          "missing", "kb"])),
        "critical_errors": int(safety[safety.target == 0].failures.sum()),
        "auto_resolve_share": round(float((pred.action == "auto_resolve").mean()), 4),
        "safe_auto_resolve_share": round(float(((pred.action == "auto_resolve")
                                                & (pred.send_mode == "auto_send")).mean()), 4),
        "n_tickets": n,
    }
    chk.to_csv(OUTPUTS / "eval_spec_checks.csv", index=False)
    per_case.to_csv(OUTPUTS / "eval_spec_cases.csv", index=False)
    safety.to_csv(OUTPUTS / "eval_safety_checks.csv", index=False)
    chk[~chk["pass"]].to_csv(OUTPUTS / "eval_misses.csv", index=False)
    (OUTPUTS / "eval_results.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


def main() -> None:
    print(json.dumps(evaluate(), indent=2))
    misses = pd.read_csv(OUTPUTS / "eval_misses.csv")
    print(f"{len(misses)} failed checks -> outputs/eval_misses.csv")


if __name__ == "__main__":
    main()
