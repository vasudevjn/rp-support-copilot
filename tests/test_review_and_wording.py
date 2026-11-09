"""Reply wording found in human review, and the human-review list wiring."""
import pandas as pd

from triage import pipeline, review
from triage.draft import templates

APOLOGY = ("sorry", "apolog", "maafi", "regret")


def test_acknowledgements_carry_no_apology():
    for cat, texts in templates()["ack"].items():
        for text in texts.values():
            assert not any(w in text.lower() for w in APOLOGY), cat


def test_threat_template_makes_no_commitment():
    t = templates()["templates"]["threat"]
    assert "contact" not in t["en"].lower() and "will" not in t["en"].lower()
    assert "sampark" not in t["hi"].lower() and "karenge" not in t["hi"].lower()


def test_fee_waiver_reply_does_not_offer_to_discuss(results):
    assert "discuss" not in results["T-0003"]["drafted_reply"].lower()


def test_frustrated_api_reply_uses_category_ack(results):
    r = results["T-0052"]
    if r["tone"] in ("frustrated", "angry"):
        assert "sorry" not in r["drafted_reply"].lower()


def test_review_file_parses():
    rows = review.load_rejections()
    assert rows and all(r.status in ("open", "fixed") for r in rows)


def test_open_rejection_blocks_sending(monkeypatch):
    monkeypatch.setattr(review, "open_rejections", lambda: {"T-9999": "test reason"})
    df = pd.DataFrame([{"ticket_id": "T-9999", "send_mode": "auto_send", "extraction_notes": ""}])
    pipeline.apply_human_review(df)
    assert df.loc[0, "send_mode"] == "do_not_send"
    assert "test reason" in df.loc[0, "extraction_notes"]


def test_output_keeps_brief_columns_first_and_adds_extractor_details():
    from triage.config import OUTPUTS
    cols = list(pd.read_csv(OUTPUTS / "triage_results.csv", nrows=1).columns)
    assert cols[:6] == pipeline.BRIEF_COLUMNS
    assert {"summary", "payment_id", "amount_inr"} <= set(cols)


def test_every_output_reply_meets_the_style_spec():
    """Regression: every final reply passes the reply_style checks (greeting, voice, length, no follow-up
    promise, empathy only when upset). Uses the evaluator's independent re-check."""
    from triage.config import OUTPUTS
    from triage.evaluate import style_violations
    out = pd.read_csv(OUTPUTS / "triage_results.csv", keep_default_na=False)
    assert style_violations(out) == []
