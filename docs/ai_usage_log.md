# AI usage log

The brief asks which AI tools were used, what they did, and what I decided.

| Date | Tool | What the AI did | What I (Vasudev) decided or checked |
|---|---|---|---|
| 2026-11-09 | Claude Code (Opus 5.5) | Read the brief, Data Pack and my spec (CLAUDE.md); scaffolded the repo; wrote config, extractor, rules engine, templates, guardrails, spikes, KB insights, evaluator, Streamlit dashboard, tests and README. | Wrote the spec and architecture (CLAUDE.md). Chose open decisions D1, D2, D3, D5, D6 and the build scope. Confirmed D7 (invoice not available -> Account Manager). To review: every template's wording, risk levels. |
| 2026-11-09 | Claude Sonnet 5.5 (runtime, via API) | Reads each ticket (category, language, tone, threat type, vagueness) and rewrites template replies for language and tone. Outputs cached. | Does not choose actions, teams or risk. Its output is checked by the guardrails and its category is overridden by auditable patterns. |
| 2026-11-09 | Claude Code (Opus 5.5) | Review pass over one reply per sub-case; proposed wording fixes (threat commitment, fee-waiver "discuss", stock apology) and the human-review list wiring; added the no-apology guardrail after the polisher re-added apologies. | Approved the fixes and supplied the API key for the re-polish. To confirm: the four "found with Claude Code" rows in `docs/replies_rejected.md`. |
| 2026-11-09 | Claude Code (Opus 5.5) | Rebuilt the dashboard from my design mockup, then applied my review changes (queue, detail view, export, logo, favicon) and added the Decision Logic tab. | Made the design mockup; chose the page structure, honest composer controls, pipeline labels, export scope, and every layout change. |
| 2026-11-09 | Claude Code (Opus 5.5) | Drafted the 11 written answers from the outputs and checked word counts. | To review and own every answer before submission. |
| 2026-11-09 | Claude Code (Opus 5.5) | Audited all 150 replies for style, wrote the reply_style spec, style guardrails, neutral escalation templates and polisher prompt v2; re-polished replies with Claude Sonnet 5.5. | Chose the greeting format, no follow-up promises, model-written empathy, and no AI reviewer or human review sheet. |
## Evaluation cases

There is no hand-labelled gold set (my decision). The expected outcomes in `eval/spec_cases.yaml` are copied
from my spec (CLAUDE.md section 13), written before the build. No AI tool invented or changed an expected value.
