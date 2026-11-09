"""Fixtures from CLAUDE.md section 13. Ticket IDs appear only in tests, never in logic."""
import re

import pytest

from triage.extract import threat_keywords

THREATS = {"T-0002", "T-0021", "T-0027", "T-0030", "T-0031", "T-0060", "T-0078", "T-0115", "T-0138"}
DATE_RE = re.compile(r"\b\d{1,2} (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b")


# ------------------------------------------------------------------ threats

def test_keyword_list_matches_exactly_the_nine_threats(tickets):
    hits = {tid for tid, r in tickets.iterrows() if threat_keywords(r.merchant_message)}
    assert hits == THREATS


@pytest.mark.parametrize("tid", sorted(THREATS))
def test_every_threat_is_critical_escalation_never_sent(results, tid):
    r = results[tid]
    assert r["action"] == "escalate"
    assert r["risk_level"] == "Critical"
    assert r["send_mode"] == "do_not_send"


def test_t0002_data_leak_police(results):
    r = results["T-0002"]
    assert r["escalation_team"] in ("Security", "Legal")
    assert r["secondary_team"] == "Legal"


def test_t0021_rbi_goes_to_legal(results):
    assert results["T-0021"]["escalation_team"] == "Legal"


def test_t0060_account_takeover_goes_to_security(results):
    assert results["T-0060"]["escalation_team"] == "Security"


def test_t0138_bribery_goes_to_legal(results):
    assert results["T-0138"]["escalation_team"] == "Legal"


def test_t0027_threat_beats_risk_review_hold(results):
    r = results["T-0027"]
    assert r["escalation_team"] == "Legal" and r["category"] == "Settlement"


# ------------------------------------------------------------------ settlements

def test_t0001_bank_mismatch_auto_resolve(results):
    r = results["T-0001"]
    assert r["action"] == "auto_resolve" and "KB-05" in r["kb_ids"]


def test_t0083_risk_review_escalates_without_reason(results):
    r = results["T-0083"]
    assert r["action"] == "escalate" and r["escalation_team"] == "Risk Ops"
    low = r["drafted_reply"].lower()
    assert "risk" not in low and "review" not in low and "fraud" not in low


def test_t0063_chargeback_reserve_escalates(results):
    r = results["T-0063"]
    assert r["action"] == "escalate" and r["escalation_team"] == "Risk Ops"
    assert "chargeback" not in r["drafted_reply"].lower()


def test_t0079_kyc_pending_auto_resolve(results):
    r = results["T-0079"]
    assert r["action"] == "auto_resolve" and "KB-04" in r["kb_ids"]


def test_t0039_delayed_shares_only_system_date(results):
    r = results["T-0039"]
    assert r["action"] == "auto_resolve"
    dates = [m.group(0) for m in DATE_RE.finditer(r["drafted_reply"])]
    assert dates == ["02 Oct 2026"]


def test_t0107_delayed_never_promises_today(results):
    r = results["T-0107"]
    assert "02 Oct 2026" in r["drafted_reply"]
    assert "today" not in r["drafted_reply"].lower()


def test_t0150_settled_cites_system_record(results):
    r = results["T-0150"]
    assert "28 Sep 2026" in r["drafted_reply"] and "63,000" in r["drafted_reply"]
    assert "today" not in r["drafted_reply"].lower()


def test_t0013_vague_settlement_answered_from_record(results):
    r = results["T-0013"]
    assert r["action"] == "auto_resolve" and r["category"] == "Settlement"


# ------------------------------------------------------------------ payments and API

def test_t0004_healthy_merchant_upi_failing_auto(results):
    r = results["T-0004"]
    assert r["action"] == "auto_resolve" and "KB-06" in r["kb_ids"]


def test_t0103_low_success_rate_escalates_payments_ops(results):
    r = results["T-0103"]
    assert r["action"] == "escalate" and r["escalation_team"] == "Payments Ops" and r["risk_level"] == "High"


def test_t0113_auth_failed_is_api_not_payments(results):
    r = results["T-0113"]
    assert r["category"] == "API & Integration" and r["action"] == "auto_resolve"
    assert "KB-14" in r["kb_ids"] and r["escalation_team"] != "Payments Ops"


def test_t0052_signature_mismatch_is_api(results):
    r = results["T-0052"]
    assert r["category"] == "API & Integration" and r["action"] == "auto_resolve" and "KB-12" in r["kb_ids"]


# ------------------------------------------------------------------ refunds, fees, missing info

def test_t0015_large_refund_escalates_no_timeline(results):
    r = results["T-0015"]
    assert r["action"] == "escalate" and r["escalation_team"] == "Refund Ops"
    assert not re.search(r"\d+\s*(-\s*\d+)?\s*(business )?days?", r["drafted_reply"])


def test_t0019_small_recent_refund_auto(results):
    r = results["T-0019"]
    assert r["action"] == "auto_resolve" and "5-7 business days" in r["drafted_reply"]


def test_t0003_fee_waiver_to_account_manager(results):
    r = results["T-0003"]
    assert r["action"] == "escalate" and r["escalation_team"] == "Account Manager"
    assert "waived" not in r["drafted_reply"].lower() and "approved" not in r["drafted_reply"].lower()


def test_t0041_missing_id_asks_for_it(results):
    r = results["T-0041"]
    assert r["action"] == "ask_info" and "merchant_id" in r["missing_fields"]
    assert "merchant id" in r["drafted_reply"].lower()


# ------------------------------------------------------------------ whole-run safety

def test_brief_columns_and_no_unsafe_sends(results):
    for r in results.values():
        assert r["guardrail_status"] in ("PASS", "PASS_AFTER_RETRY", "FAIL_NEEDS_HUMAN")
        if r["action"] == "escalate":
            assert r["send_mode"] != "auto_send"
        if r["guardrail_status"] == "FAIL_NEEDS_HUMAN":
            assert r["send_mode"] == "do_not_send"


def test_evaluate_runs_with_zero_critical_errors(results):
    from triage.evaluate import evaluate
    res = evaluate()
    assert res["critical_errors"] == 0
    assert res["spec_cases"] == 21
