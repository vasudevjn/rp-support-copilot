"""Guardrail unit tests from CLAUDE.md section 13."""
from triage.guardrails import run_all
from triage.lookup import get_merchant

DELAYED = get_merchant("M1003")   # Delayed, expected 02 Oct 2026


def _run(reply, *, action="auto_resolve", sub_case="settlement_delayed", kb=("KB-02",), merchant=DELAYED,
         message="Where is my settlement? M1003", language="English"):
    return run_all(reply, message=message, merchant=merchant, action=action, sub_case=sub_case,
                   kb_ids=list(kb), missing_fields=[], language=language, send_mode="auto_send")


def test_system_date_passes():
    assert _run("Your expected settlement date is 02 Oct 2026. Razorpay Support").passed


def test_invented_date_fails():
    g = _run("Your settlement will arrive on 05 Oct 2026. Razorpay Support")
    assert not g.passed and "dates" in "".join(k for k, v in g.checks.items() if v != "PASS")


def test_release_today_promise_fails():
    g = _run("We will release your payout today. Razorpay Support")
    assert not g.passed


def test_refund_approved_fails():
    g = _run("Good news, refund approved. Razorpay Support", sub_case="refund_in_window", kb=("KB-07",))
    assert not g.passed


def test_kb12_paise_conversion_passes():
    g = _run("Amounts must be sent in paise, so Rs 499 should be sent as 49900. Razorpay Support",
             sub_case="api_amount_mismatch", kb=("KB-12",),
             message="Getting BAD_REQUEST_ERROR: order amount mismatch. Amount is 499. M1033",
             merchant=get_merchant("M1033"))
    assert g.passed, g.failures


def test_kb04_conditional_release_passes():
    g = _run("Settlements are released within 1 business day of KYC being verified. Razorpay Support",
             sub_case="settlement_kyc_pending", kb=("KB-04",), merchant=get_merchant("M1038"))
    assert g.passed, g.failures


def test_escalation_with_duration_fails():
    g = _run("We have escalated this; you will hear back in 5-7 business days. Razorpay Support",
             action="escalate", sub_case="refund_large_escalate", kb=("KB-07",))
    assert not g.passed


def test_risk_hold_reply_must_not_leak_reason():
    g = _run("Your payout is on hold due to a risk review. Razorpay Support", action="escalate",
             sub_case="settlement_hold_escalate", kb=("KB-03",), merchant=get_merchant("M1020"))
    assert not g.passed


def test_language_mismatch_fails():
    g = _run("Your expected settlement date is 02 Oct 2026. Razorpay Support", language="Hinglish")
    assert not g.passed


def _threat(reply):
    return run_all(reply, message="I will send a legal notice. M1034", merchant=get_merchant("M1034"),
                   action="escalate", sub_case="threat", kb_ids=["KB-15"], missing_fields=[],
                   language="English", send_mode="do_not_send")


def test_threat_reply_with_apology_fails():
    g = _threat("I'm sorry for the frustration this has caused. We have shared your message with the right "
                "specialist team. Razorpay Support")
    assert not g.passed


def test_threat_reply_without_apology_passes():
    g = _threat("Thank you for writing to us. We have shared your message with the right specialist team, "
                "who will review it. Razorpay Support")
    assert g.passed, g.failures


def test_apology_fails_in_any_reply():
    from triage.guardrails import check_apology
    assert check_apology("I understand, and I'm sorry for the worry this causes.")
    assert check_apology("Iske liye maafi chahte hain.")
    assert not check_apology("I know waiting on a payout affects your business.")


# ------------------------------------------------------------------ reply style (config reply_style)
from triage.guardrails import (check_commitments, check_empathy_scope, check_exclamation,  # noqa: E402
                               check_greeting, check_length, check_signoff, check_voice)

GOOD = "Hi Sahara Naturals team,\nAs per our system, the expected settlement date is 02 Oct 2026.\n\nRazorpay Support"


def test_greeting_must_be_first_line():
    assert not check_greeting(GOOD, "Hi Sahara Naturals team,")
    assert check_greeting("Hi! As per our system...\n\nRazorpay Support", "Hi Sahara Naturals team,")


def test_signoff_required():
    assert not check_signoff(GOOD)
    assert check_signoff("Hi,\nThanks.")


def test_length_limit_counts_body_only():
    assert not check_length(GOOD)
    assert check_length("Hi,\n" + "word " * 81 + "\n\nRazorpay Support")


def test_follow_up_promise_fails():
    assert check_commitments("Hi,\nOur team will get back to you.\n\nRazorpay Support")
    assert check_commitments("Namaste,\nWoh aapko update karenge.\n\nRazorpay Support")
    assert not check_commitments("Hi,\nWe have passed this to our Payments team, who are reviewing it.\n\nRazorpay Support")


def test_voice_is_we_in_english():
    assert check_voice("Hi,\nI understand this is urgent.\n\nRazorpay Support", "English")
    assert not check_voice("Hi,\nWe understand this is urgent.\n\nRazorpay Support", "English")


def test_no_exclamation():
    assert check_exclamation("Hi,\nGreat news!\n\nRazorpay Support")
    assert not check_exclamation(GOOD)


def test_empathy_only_for_upset_merchants():
    upset = "Hi,\nWe understand this is urgent. Here is the status.\n\nRazorpay Support"
    assert check_empathy_scope(upset, "calm")
    assert not check_empathy_scope(upset, "frustrated")
