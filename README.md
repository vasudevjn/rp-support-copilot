# Merchant Support Triage Copilot

Razorpay Campus AI Build-a-thon, Problem 1. For each of the 150 merchant tickets it picks a category, decides
an action (auto-resolve, ask for info, or escalate to a team), drafts a reply in the merchant's language
style (English or Hinglish) from that merchant's own record and the KB, and flags risk.

**Principle: the LLM reads, rules decide, templates write, the checker blocks, humans own escalations.**

## Quick start

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows; use source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
pip install -e .
cp .env.example .env              # then add ANTHROPIC_API_KEY (optional)
python -m triage.pipeline         # uses cached LLM outputs; offline reader if no key and no cache
python -m triage.pipeline --refresh-llm   # re-calls Claude for every ticket and refreshes the cache
python -m triage.pipeline --offline       # keyword reader + templates only, no LLM at all
python -m triage.evaluate                 # spec cases + safety checks -> outputs/eval_*
python -m triage.report                   # rewrites the Results section below from outputs/
pytest -q
streamlit run app/streamlit_app.py
```

## Dashboard

`streamlit run app/streamlit_app.py` (light theme in `.streamlit/config.toml`). The layout follows the design mockup.
Every number is read from `outputs/`, and all logic is imported from `src/triage`.

| Page | What it shows |
|---|---|
| Overview | Outcome counts, safe auto-resolve share, threats caught, send-mode split, categories, and the critical and high-risk tickets to look at first. |
| Ticket Queue | All 150 tickets in one table. View tabs (Needs Review, Escalations, Awaiting Information, Auto-Send) and filters narrow the same list; click a ticket to open it. Export To Excel downloads all 150 tickets. |
| Ticket Workspace | One ticket in two columns: the message and the key merchant facts (with the success-rate gauge for payment tickets) on the left; the recommendation, why, the KB article, the drafted reply, its guardrail result and the audit trail on the right. |
| Insights & Quality | Insights: escalations by team, spikes, KB articles to improve, unsupported queries, ask-info reasons, churn signals. Decision Logic: every escalation and ask-info rule that fired, with counts and an example ticket, plus tone handling. Quality: spec cases, safety checks, guardrail retries, critical tickets, and replies not sent. Nothing repeats the Overview. |
| Try It | Paste a new ticket and run the real pipeline live (capped per session). |

## How a ticket flows

```
Ticket
 -> Extractor     regex: merchant ID, payment ID, amount, days.  LLM (cached): category, language, tone,
                  threat type, vagueness.  Config intent patterns win on category; LLM covers new phrasing.
 -> Threats       keyword list (config) OR LLM threat flag -> escalate. Either one fires (fail safe).
 -> Lookup        merchant record: settlement status, hold reason, dates, success rate, chargebacks, KYC.
 -> Rules         KB as a decision table (src/triage/rules.py, config/rules.yaml). First match wins.
 -> Draft         template per sub-case (templates/*.yaml), slots filled from data -> LLM polish (cached)
                  for language and tone only.
 -> Guardrails    dates, durations, numbers, promise phrases, internal reasons, threat rules, ask-info fields,
                  language, slot values. Fail -> regenerate once -> fail again -> FAIL_NEEDS_HUMAN, do_not_send.
 -> Send mode     auto_send / agent_review / do_not_send. Threats are never auto-replied.
```

### Escalation rules (priority order)

1. **Threat** (KB-15): legal, regulator, fraud or bribery allegation, media, data leak, account takeover ->
   Legal or Security, Critical, `do_not_send`.
2. **Missing merchant ID** (KB-16) -> ask for it before anything else.
3. **Too vague** -> ask for specifics, unless the topic is settlement and the record answers it.
4. **Settlement**: Settled / Delayed / KYC pending / bank mismatch -> auto-resolve from the system record;
   Risk review or Chargeback reserve hold -> Risk Ops, reason never shared.
5. **Payment failure**: success rate below 85% -> Payments Ops; else KB-06 advice
   ("money deducted" without a payment ID -> ask for it).
6. **Refund**: Rs 1,00,000 or more -> Refund Ops, no timeline; past 7 business days -> Refund Ops; else 5-7 days.
7. **Chargeback** (KB-08) -> auto-resolve; dispute debit with 0 open chargebacks -> ask for the debit reference.
8. **KYC**: document list -> auto; "is this message genuine?" from a Verified merchant -> Security.
9. **Fees**: invoice -> auto (or Account Manager if the system shows none); waiver, MDR or fee refund -> Account Manager.
10. **API**: KB-12/13/14 fixes -> auto; no KB match (5xx, rate limits, timeouts, blank popup) -> Tech Support.
11. **Account**: contact or name change -> auto (KB-11); closure -> Account Manager + Risk Ops.

Angry or urgent tone raises risk one level (max High) and forces agent review. Tone never changes the action.
Every row carries a `decision_trace` in plain words and the KB articles it rests on.

## Results

<!-- RESULTS:START -->
_Generated by `python -m triage.report` from `outputs/` (run 2026-11-09T12:29:10+00:00, config v0, extraction sources {'cache': 150}, reply sources {'cache': 141, 'template': 9})._

| Measure | Value |
|---|---|
| Tickets triaged | 150 |
| Action: auto_resolve | 89 (59%) |
| Action: ask_info | 18 (12%) |
| Action: escalate | 43 (29%) |
| Safe auto-resolve (auto_resolve and auto_send) | 60 (40%) |
| Threat tickets escalated / marked do_not_send | 9 / 9 of 9 |
| Replies blocked by guardrails (FAIL_NEEDS_HUMAN) | 0 |
| Replies passed after one regeneration | 0 |
| Escalations set to auto_send | 0 |

**Escalations by team:** Payments Ops 10, Account Manager 7, Refund Ops 7, Legal 6, Security 5, Tech Support 4, Risk Ops 4

**Send mode:** agent_review 72, auto_send 69, do_not_send 9

**Evaluation** (`python -m triage.evaluate`): spec cases are the expected outcomes written in the spec before the build (`eval/spec_cases.yaml`); they cover the risky paths on purpose and are not a random-sample accuracy estimate.

| Metric | Value |
|---|---|
| Spec cases fully passed | 21 / 21 |
| Spec checks passed | 62 / 62 |
| Action / team / category / risk checks | 19/19 / 10/10 / 3/3 / 6/6 |
| Reply content checks | 19/19 |
| Critical errors over all 150 tickets | 0 |
<!-- RESULTS:END -->

## Outputs (`outputs/`)

| File | What it is |
|---|---|
| `triage_results.csv` / `.xlsx` | All 150 tickets. First six columns are exactly the brief's table. |
| `escalations.csv` | Escalated tickets by team, with holding replies. |
| `replies_not_sent.csv` | Replies I would not send, and why (threat drafts, guardrail failures). |
| `guardrail_log.csv` | Every guardrail check on every attempt. |
| `spikes.csv`, `spikes_daily.csv`, `spikes_repeat_merchants.csv` | Payment-failure spike signals. |
| `kb_insights.csv`, `kb_gaps.csv` | KB articles to improve, tickets no article covered. |
| `safety_checks.json` | Critical-error counts written by the pipeline. |
| `eval_results.json`, `eval_spec_cases.csv`, `eval_spec_checks.csv`, `eval_safety_checks.csv`, `eval_misses.csv` | Spec-case checks, whole-run safety checks, every failed check. |
| `run_metadata.json` | Run time, config version, model, prompt versions, data file hash. |

## Reproducibility

All LLM outputs are cached in `cache/` keyed by prompt version, model and input, so a rerun gives identical
results. Claude Sonnet 5.5 does not accept a custom temperature, so the cache (not temperature 0) is what makes
runs repeatable. Re-calling the LLM needs the explicit `--refresh-llm` flag. `run_metadata.json` records the
data file hash, config version, model and prompt versions.

## Honesty notes

- No baseline data (handle time, volumes, CSAT) is provided; any "today" figure in the pitch is an assumption.
- There is no hand-labelled gold set, so no accuracy figure is claimed for all 150 tickets. The spec cases are
  the same expected outcomes the unit tests encode, so passing them shows the rules do what the spec says, not
  that the spec matches the graders' hidden answers.
- Decisions and their reasons: `docs/decisions_log.md`. What AI did vs what I decided: `docs/ai_usage_log.md`.
