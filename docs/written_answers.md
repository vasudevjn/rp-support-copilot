# Written answers: Problem 1 (Merchant Support Triage Copilot)

Every number below comes from `outputs/` (run of 09 Nov 2026, model `claude-sonnet-5-5`, cached).
Anything about "today" is an assumption, because the Data Pack has no support baseline.

---

## General questions

### 1. Which problem did you pick, and who is the main user?

I picked Problem 1, the merchant support triage copilot. The main user is the Customer Success support agent. For each ticket, the copilot names the category, looks up the merchant's record, chooses auto-resolve, ask for information or escalate, drafts a reply in the merchant's English or Hinglish, and flags risk. The agent reviews and sends. Specialist teams (Legal, Security, Risk Ops, Refund Ops, Payments Ops, Account Manager, Tech Support) get the escalations with a holding draft. The merchant benefits next, with a faster and correct reply in their own style. The agent's pain today is repetitive tickets, several merchant fields to check on each one, and strict KB rules that are easy to break under pressure, such as promising a date, refund or release. Legal and security threats also sit in the normal queue: 9 of the 150 tickets are threats.

### 2. What does a good outcome look like in numbers today, and what does your solution change?

Assumption, since no baseline is given: today an agent reads every ticket and checks several merchant fields by hand, so all 150 tickets need a person. A good outcome is zero critical errors, every threat escalated, every ticket without an ID asked for it, and a high share closed safely without an agent. On the 150 tickets my solution gives:

- 89 auto-resolve, 18 ask for information, 43 escalate.
- 60 tickets (40%) are safe to send with no human: auto-resolved, calm in tone, and passed every guardrail.
- 72 drafts go to an agent for a quick review instead of being written from scratch.
- 9 of 9 threats are escalated and marked do-not-send.
- 0 critical errors in the safety checks.
- Escalations by team: Payments Ops 10, Refund Ops 7, Account Manager 7, Legal 6, Security 5, Tech Support 4, Risk Ops 4.

### 3. What does AI do in your solution, and what is deliberately left to rules or humans? Why?

The rule is simple: the LLM reads, rules decide, templates write, a checker blocks, and humans own escalations. Claude reads each message for category, language, tone and threat type, then rewrites a filled template into the merchant's English or Hinglish and tone. Code makes every decision: the action, the team and the risk, using KB rules in priority order with merchant data from the system. Dates, amounts and steps are filled into templates by code, never by the LLM. A Python checker blocks invented dates, durations not backed by the KB, promise phrases and internal hold reasons. Humans review every escalation, every frustrated or angry ticket, and every threat. Why: the KB is effectively a decision table, so rules are more accurate and can be traced to a KB article in every case. A wrong promise is costly, so no LLM output reaches a merchant unchecked.

### 4. Which tools and models did you use, and why those?

- **Python with pandas and PyYAML** for the pipeline. Every threshold, team name and keyword list sits in one config file, so I can change a rule without touching code.
- **Claude Sonnet 5.5 through the Anthropic API** for reading tickets and polishing reply wording. It handles Hinglish well. It accepts no temperature setting, so every output is cached with the prompt version and model ID, and judges get identical results without the API.
- **Streamlit and Plotly** for a dashboard the agent can actually use: overview, ticket queue, ticket detail, insights and quality, and a live Try It page.
- **pytest** for 60 tests.
- **Claude Code (Opus 5.5)** as my coding assistant. I wrote the spec and made the policy decisions, and it wrote most of the code. Both roles are logged in `docs/ai_usage_log.md`.

### 5. How did you test it? Show results on at least 20 cases, including the ones it got wrong.

Three layers:

1. **21 spec cases (62 checks)**, with expected outcomes written in my spec before the build. All 21 pass: action 19/19, team 10/10, category 3/3, risk 6/6, reply content 19/19. The appendix lists each case.
2. **10 safety checks across all 150 tickets**, such as a threat not escalated, an escalation auto-sent, a promise phrase, or a reply-style violation. Zero failures.
3. **Reproducibility.** Reruns from the cache give byte-identical outputs.

What went wrong:

- 7 of the 9 threat drafts carried an apology (see Q6).
- A new style rule broke spec case T-0083: "reviewing" echoed "Risk review". Fixed.
- My own read rejected three more wordings, now fixed and listed.
- Claude read tone differently from my keyword reader on 24 tickets.

Honestly, the spec cases double as my tests, so they are not a random-sample accuracy estimate.

### 6. Describe one real failure or edge case, what it could have cost, and how your design handles it.

**What happened.** The threat template has no apology, but for angry merchants the LLM polisher added one. 7 of the 9 threat drafts opened with "I'm sorry for the frustration this has caused", including the RBI complaint and the bribery allegation. My guardrail missed it, because its banned list only covered explicit admissions such as "our fault".

**What it could have cost.** KB-15 says never admit fault on a threat. Legal could read the apology as an admission, and sending it would be a critical error.

**How the design handled it.** The drafts were already do-not-send, so a human would have seen them first.

**What I fixed.** Threat replies now skip the LLM and use the fixed template. "Sorry", "apolog", "regret", "maafi" and "khed hai" are banned in threat replies, with two tests.

**Lesson.** An LLM that only rewrites wording can still change the meaning, so risky replies stay deterministic.

### 7. What are the risks (wrong answer, bias, compliance, privacy), and what controls did you add?

- **Wrong answer.** Rules decide, not the LLM, and each decision traces to a KB article. If the LLM and regex disagree on an ID or amount, the regex wins. Tickets the KB does not cover are escalated, never guessed.
- **Over-promising.** Every reply passes 18 checks. Dates must match the merchant's record. Durations must be KB-backed. Every number needs a source. Promise and follow-up phrases are banned. A failing reply is regenerated once, then blocked.
- **Unprofessional tone.** Style rules enforce a fixed greeting, "we" voice, no exclamation marks, and empathy only for upset merchants.
- **Compliance.** Threats are never auto-sent. Risk-hold replies never hint at the reason. Suspicious KYC messages go to Security.
- **Bias.** English and Hinglish get the same rules. Tone changes only wording and review, never the action.
- **Privacy.** Synthetic data only, a private repo, and no keys committed.

### 8. If you had 3 months and a small team, what would you build next, and how would you know it worked?

- **Month 1: shadow mode.** The copilot runs beside real agents but sends nothing. I measure agreement with the agent on category, action and team, and log every draft the agent edits or rejects, with the reason.
- **Month 2: go live on the safest sub-cases**, such as delayed settlements, in-window refunds and API fixes, where agreement clears an agreed bar. Rejected drafts feed template and rule changes. Live payment data lets a spike alert reach Payments Ops the same day.
- **Month 3: KB rewrites** for the top gaps found here: when to ask for a payment ID (KB-16), calendar versus business days and overdue refunds (KB-07), and articles for 502 errors, rate limits and timeouts (KB-12).

**How I would know it worked:** handle time and first-response time fall, reopen rate and CSAT hold or improve, and critical errors stay at zero.

## Problem 1 questions

### P1-a. How do you decide when to escalate?

KB rules in priority order; the first match wins:

1. **Threats (KB-15):** legal, regulator, fraud, bribery, media, data leak, account takeover. A keyword list or an LLM flag, either one, triggers it. Legal or Security, Critical, do-not-send.
2. **Risk review or chargeback reserve hold (KB-03):** Risk Ops, reason never shared.
3. **Payment failures below 85% 7-day success rate (KB-06):** Payments Ops, possible degradation.
4. **Refunds of Rs 1,00,000 or more, or past 7 business days (KB-07):** Refund Ops.
5. **Waivers, MDR changes or a missing invoice (KB-09):** Account Manager.
6. **Account closure (KB-17):** Account Manager, plus Risk Ops.
7. **API errors with no KB article:** Tech Support.

Every escalation gets a holding reply with no timeline and no follow-up promise. The merchant's data decides, so the same message can split: "UPI failing" auto-resolves at 91.5% success and escalates at 76.3%. In total, 43 of 150 tickets escalated.

### P1-b. What share of tickets can be safely auto-resolved, and at what accuracy?

89 of 150 tickets (59%) are auto-resolved. I count only 60 (40%) as safe to send with no human, because each is calm in tone and passed every guardrail. The other 29 are frustrated, so an agent checks the draft first, even though the answer comes from the KB.

**Accuracy.** All 21 spec cases pass (62 of 62 checks), including the keyword traps: "Authentication failed" from a merchant at 84% goes to API & Integration, not Payments Ops. The safety checks show 0 critical errors across all 150 tickets: no invented dates, no promised refunds or waivers, and no threat auto-sent.

To be honest about the limits, those 21 cases come from my own spec, not a random sample. Without gold labels I cannot claim accuracy against the hidden answers. Shadow mode would give the real number.

### P1-c. What does your solution do when a merchant is angry or the message is ambiguous?

**Angry or frustrated.** Claude reads the tone (88 calm, 54 frustrated, 8 angry). Angry or urgent tickets go up one risk level, capped at High. No upset merchant is auto-sent; an agent sees each one. The reply opens with one short empathy sentence about their problem, with no apology, and tone never changes the facts or the action: "I need it today" still gets the system date, never "today".

**Ambiguous.** The 6 tickets with no merchant ID are asked for it first (KB-16). Vague messages like "Payment failed." get a request for the payment ID, what is failing and since when. If the merchant record already answers it, as with "Settlement issue" from a settled merchant, the reply uses the data. If the message conflicts with the data, such as a dispute debit with 0 open chargebacks, the reply asks for the debit reference. 18 tickets were asked for information.

## Appendix: results on the 21 spec cases (for Q5)

| Ticket | Case | Checks passed |
|---|---|---|
| T-0002 | Data leak, going to police | 4/4 |
| T-0021 | Complained to RBI | 4/4 |
| T-0060 | Account takeover, bank account changed | 4/4 |
| T-0138 | Staff asked for a commission | 4/4 |
| T-0027 | Risk review hold plus legal notice: threat rule wins | 4/4 |
| T-0001 | Bank account mismatch hold | 2/2 |
| T-0083 | Risk review hold, reason never shared | 5/5 |
| T-0063 | Chargeback reserve hold | 2/2 |
| T-0079 | KYC pending hold | 2/2 |
| T-0039 | Delayed: share the system date only | 2/2 |
| T-0107 | Delayed, merchant wants it today | 2/2 |
| T-0150 | Settled, Rs 63,000 pending, need today | 3/3 |
| T-0013 | Vague "Settlement issue" answered from the record | 2/2 |
| T-0004 | UPI failing, 91.5% success rate | 2/2 |
| T-0103 | UPI failing, 76.3% success rate | 3/3 |
| T-0113 | Authentication failed from an 84.0% merchant (keyword trap) | 3/3 |
| T-0052 | SIGNATURE_MISMATCH (keyword trap) | 3/3 |
| T-0015 | Refund Rs 2,50,000 | 3/3 |
| T-0019 | Refund Rs 12,000, 3 days old | 2/2 |
| T-0003 | Fee waiver request | 4/4 |
| T-0041 | "Payment problem. Fix urgently." with no ID | 2/2 |
