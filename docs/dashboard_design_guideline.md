# Dashboard Design Guideline: Support Copilot

For Claude Code. Read this with `CLAUDE.md`. This file **replaces CLAUDE.md section 16 (Dashboard spec)**. Everything else in CLAUDE.md still applies, especially: the dashboard imports from `src/triage` and never reimplements logic, and no number is ever invented.

Visual reference: the Design canvas "Razorpay Support Copilot Dashboard" (4 artboards: Overview, Ticket Queue, Ticket Workspace, Insights & Quality). Match its structure, spacing and wording. Build it in Streamlit.

## 1. Principles

1. The product is ticket processing. Analytics is secondary.
2. The Ticket Workspace is the centrepiece. Spend the effort there.
3. Four screens only. Merchant details, KB articles and the audit trail are dialogs, not pages.
4. Every number on screen is computed from `outputs/` (CSV or JSON). No hardcoded counts, no rounding up. If a file is missing, show an empty state, never a placeholder number.
5. Threats can never be sent from the UI. Sending is disabled, not hidden.

## 2. Changes from the earlier spec

- Four screens, not seven. Removed: Escalation Board, Evaluation page, Try It. (Evaluation numbers move into Insights & Quality. Try It can return later as an optional fifth page, not now.)
- No Settings page or sidebar link anywhere.
- App name in the sidebar is **Support Copilot**. No "Razorpay" in the app name or page titles.
- The Response Composer has **no language or tone selectors**. Language and tone are detected and shown as read-only facts in Ticket Details.
- Draft replies keep their real sign-off, "Razorpay Support". It comes from the pipeline output. Do not change it.

## 3. Navigation

Use `st.navigation` with exactly three entries:

| Label | Page file |
|---|---|
| Overview | `app/pages/overview.py` |
| Ticket Queue | `app/pages/ticket_queue.py` |
| Insights & Quality | `app/pages/insights.py` |

The Ticket Workspace is not in the sidebar. It opens when a ticket is selected in the queue, an Overview priority row, or any ticket link in Insights. Pass the ticket ID with `st.session_state["selected_ticket"]` and a `st.query_params["ticket"]`, so a workspace link is shareable. Keep "Ticket Queue" highlighted while the workspace is open, with a "Ticket Queue" back link at the top.

Sidebar: app mark, the name "Support Copilot", then the three links. Nothing else. Dark navy sidebar, active item has a lighter navy fill and white bold text.

## 4. Visual system

Apply through one `app/theme.py` that injects CSS once, plus `.streamlit/config.toml` for base colours. Do not scatter inline styles through pages.

**Fonts:** Inter for text, Space Grotesk for page titles and big numbers. Numbers use tabular figures.

**Colour tokens**

| Token | Hex | Use |
|---|---|---|
| page background | `#F4F6F9` | app background |
| surface | `#FFFFFF` | cards, tables |
| ink | `#101828` | body text |
| muted | `#556070` | helper text, labels |
| line | `#E1E5EB` | card borders, dividers |
| sidebar | `#0E1526` | sidebar background |
| sidebar active | `#1E2C52` | active nav item |
| accent | `#2B55D9` | primary buttons, links, Resolve outcome |
| accent tint | `#E8EEFD` | KB chips, active tab chip |

**Risk chips** (always show the word, never colour alone): Critical = solid `#B42318` with white text. High = `#FFE6D5` on `#9A3412`. Medium = `#FFF1C2` on `#6E5200`. Low = `#EAEDF2` on `#3F4A5A`.

**Outcome colours:** Resolve `#2B55D9`, Ask for info `#E39A1B`, Escalate `#5B2A86`.

**Send status chips:** Ready for approval = `#DDF3EA` on `#175C43`. Needs review = `#DCEBFB` on `#1D4E89`. Do not send = `#FDE0DD` on `#8A1C13`.

**Shape:** cards have a 1px `line` border, 12px radius, 20 to 24px padding, no shadows. Buttons and inputs are at least 44px tall with an 8px radius. Page content padding 32px. Visible focus ring in accent colour. Text contrast at least 4.5:1.

**No:** emoji, gradients, left-border accent cards, em-dashes in UI copy.

**Copy rules** (kept from before): Title Case for page names, section headers and buttons. Small section labels are ALL CAPS with letter spacing. Helper text in sentence case. Short, simple sentences.

## 5. Shared definitions

Compute these once in `src/triage` (or a small `app/data.py` that wraps it) and reuse everywhere, so the same number never differs between screens.

| Term | Definition |
|---|---|
| Resolved | `action == auto_resolve` |
| Awaiting information | `action == ask_info` |
| Escalated | `action == escalate` |
| Critical or high | `risk_level in {Critical, High}` |
| Ready for Approval (status) | `send_mode == auto_send` |
| Needs Review (status) | `send_mode in {agent_review, do_not_send}` |
| Do not send (status) | `send_mode == do_not_send` |
| Guardrail blocks | tickets whose first attempt failed in `guardrail_log.csv` (`attempt == 1` and `passed == False`), shown with how many then passed on retry and how many ended `FAIL_NEEDS_HUMAN` |
| Manual reviews | count of Needs Review (agent review plus do not send) |

Status labels in the UI: send_mode `auto_send` shows "Ready for approval", `agent_review` shows "Needs review", `do_not_send` shows "Do not send". Action labels: "Resolve", "Ask for info", "Escalate". Team shows "None" when empty.

If you change any definition, record it in `docs/decisions_log.md`.

## 6. Screen 1: Overview

Landing page. Title "Overview", subtitle with the date range read from the data.

- **Primary button** top right: "Go to Ticket Queue".
- **KPI cards (4):** Total tickets, Resolved, Awaiting information, Escalated. Each has a one-line note computed from data (for example channel split, or "N of these are threats").
- **Triage outcomes:** one horizontal stacked bar (Resolve, Ask for info, Escalate) with a legend showing count and percent.
- **Ticket volume by category:** horizontal bars, count at the right, sorted descending.
- **Needs attention first:** list of Critical tickets first, then High, capped at 6 rows. Each row: ticket ID, merchant, one-line issue, team, risk chip. Row opens the workspace. Footer link "See all N in the queue" opens the queue pre-filtered to Critical and High. Note below the list: critical tickets are threats, and the copilot only drafts a holding reply and never sends it.

Layout: KPI row on top; below it two columns (charts left, priority list right). Wrap to one column on narrow screens.

Use plotly with the colours above, or plain HTML bars if simpler. Chart text at least 12px.

## 7. Screen 2: Ticket Queue

The core screen. All 150 tickets, searchable and filterable.

**Tabs** (each with a count chip): All Tickets, Needs Review, Escalations, Awaiting Information, Ready for Approval. Tabs are views over the same table. Definitions in section 5.

**Controls row:** search box (ticket ID, merchant, issue text), then filters: Category, Risk, Action, Language, Status. Filters combine with the active tab.

**Table columns, in order:** Ticket, Merchant, Issue, Category, Risk, Action, Team, Status.

- Merchant is the business name from `P1_Merchants`. For tickets with no merchant ID show "No merchant ID".
- Issue is a short plain summary. Use the extractor's `summary` field if present; otherwise truncate `merchant_message` to about 60 characters. Never invent text.
- Default sort: risk (Critical first), then ticket number.
- Risk and Status render as chips. Click a row to open its workspace.
- Footer line: "Showing N of 150 tickets."
- Empty state: "No tickets match these filters."

Implementation note: `st.dataframe` cannot render chips. Either use `st.column_config` with text labels plus row selection, or render a custom HTML table. Whichever you choose, rows must be keyboard reachable.

## 8. Screen 3: Ticket Workspace (centrepiece)

Header: back link "Ticket Queue", ticket ID as the page title, a risk chip ("Critical risk", "High risk" and so on) and a category chip. Previous and next ticket buttons within the current queue view are welcome.

**Critical banner.** If `risk_level == Critical` or `send_mode == do_not_send`: show a full-width solid red banner above the panels: "Critical threat. Sending is disabled." with one sentence: the ticket goes to the named team, the reply is a holding draft for them to approve, and the copilot never replies to threats on its own.

Three panels in a row (`st.columns([1, 1.3, 1.2])`), stacking on narrow screens.

### Left: Ticket Details
- **Merchant message** in a tinted box.
- Ticket ID, Received, Channel, Language, Tone (all read-only).
- **Extracted details:** Merchant (business name, a button that opens the Merchant dialog), Merchant ID, Payment ID ("Not in message" if none), Amount ("Not in message" if none), Issue summary. For threats, also Threat type and the matched keywords.
- **Conversation:** "No earlier messages on this ticket. This is the first contact." Show real history only if the data has it.

### Centre: AI Analysis
- **Recommended action** as a large heading, for example "Escalate to Payments Ops", with "Category · sub-case" beneath. For resolve and ask-info show "Resolve" or "Ask the merchant for more information".
- Three small tiles: Category, Risk, Send mode.
- **Why this action?** Plain-language explanation. Source it from `decision_trace`. Rewrite for readability only if you can keep every fact and number identical. Below it, a muted line naming the rule that fired (for example "Rule 5 · Payment Failure · first matching rule wins").
- **Knowledge base:** one chip per cited `kb_ids` value, labelled "KB-06 · Payment failures". Clicking opens the KB dialog.
- **Merchant data:** the fields that support the decision. When the decision is the 85% success-rate rule, show a gauge: bar to the merchant's rate with a marker at the threshold read from `config/rules.yaml`. Then a key-value list (settlement status and hold, KYC status, open chargebacks, refunds in process). Add the note "The success rate decided this action. The other fields are context only." Pick the decisive field from the rule that fired, not from a hardcoded ticket. For threat tickets, show the record with the note "Not used for this decision. A threat is escalated whatever the merchant record says."
- Link "Open M#### " opens the Merchant dialog.

### Right: Response Composer
- **No language or tone selectors.**
- **Drafted reply** in a text area, read-only by default. Label it with the draft type, for example "(holding reply, English)".
- **Guardrail check:** a PASS or FAIL chip, then the checklist from `guardrail_log.csv` for that ticket (Dates, Durations, Numbers, Promise phrases, Internal reasons, Language match). Show failing checks with the failure reason text.
- **Buttons:**
  - Approve & Send: primary, full width. Enabled only when `send_mode != do_not_send` and `guardrail_status` is not `FAIL_NEEDS_HUMAN`. When disabled the label is "Sending disabled for threats" (or "Blocked by guardrails" for a guardrail failure).
  - Edit: toggles the text area to editable. Label becomes "Done editing".
  - Regenerate: re-runs the polisher for this ticket through the pipeline (needs the explicit refresh path from CLAUDE.md section 10, and the guardrails must run again on the new draft). Show the new guardrail result.
  - Escalate to another team: opens a team picker limited to the teams in `config/rules.yaml`.
- A link "View audit trail" opens the audit dialog.
- Status messages appear in one inline area under the checklist.

**Important behaviour rules**
- Approve & Send must not call any external system. It records an agent action (ticket ID, action, timestamp, edited or not, the final text) to `outputs/agent_actions.csv` and shows "Reply approved and sent." Be clear in code comments and in the README that nothing is actually transmitted. This is a human-in-the-loop log.
- An edited reply must pass the guardrail checker again before Approve & Send is enabled. If it fails, show the reasons and keep sending disabled.
- Never allow a threat ticket to be approved, even if someone edits state or query params.

### Dialogs (use `st.dialog`)
- **Merchant dialog:** business name, merchant ID, city, segment, industry, KYC status, settlement status (and hold reason and since-date when on hold), last settlement date and amount, 7-day payment success rate, open chargebacks, refunds in process, and a list of the merchant's tickets (ID, category, date, each linking to its workspace). All from `P1_Merchants` and the results table. The agent may see the hold reason here, but it must never appear in a reply to the merchant (CLAUDE.md section 8.4). Add the line "Internal view. Do not share with the merchant."
- **KB dialog:** article ID, title, and the article text **verbatim** from `P1_KnowledgeBase`. Add the line "The knowledge base is the rulebook. The copilot applies it and never overrides it."
- **Audit trail dialog:** numbered steps for that ticket: Extraction, Threat check, Merchant lookup, Rule fired, Reply drafted, Guardrails, Agent actions. Fill each from real fields (`extraction_source`, `threat_keywords`, `decision_trace`, `reply_source`, guardrail log rows, `agent_actions.csv`). If a step has no data, say "No data" rather than inventing text.

## 9. Screen 4: Insights & Quality

Supervisor view. Keep it simple. Plain cards, minimal chart styling.

1. **KPI cards (4):** Tickets processed, Escalations, Guardrail blocks, Manual reviews. Notes: "Across N specialist teams", "First drafts rewritten, N passed", "N agent review, N do not send".
2. **Ticket categories** (bars) beside **Triage outcomes** (stacked bar) with **Escalations by team** (bars) under it.
3. **Daily tickets and payment failures:** 30 columns for the month. Light bar is all tickets, dark overlay is payment-failure tickets. Label the peak payment-failure day. Underneath, one sentence naming the peak day and any merchants flagged by the repeat rule. Both come from `outputs/spikes.csv` and the thresholds in config, not from hardcoded dates or merchant IDs.
4. **Knowledge base articles to improve:** ranked list from `outputs/kb_insights.csv` (`improvement_score`, `notes`). Show ID, topic, a one-line note, score.
5. **Unsupported queries:** tickets with `no_kb_match`, each with ID and message summary, linking to the workspace.
6. **Why the copilot asked for more information:** bars grouped by `missing_fields` value.
7. **Critical tickets:** all of them, with ID, short issue, team. Sentence above: all are escalated, marked do not send, holding draft only.
8. **Guardrail blocks:** every ticket whose first draft failed, the failing check and reason from the log, and whether it passed on retry. Also list any `FAIL_NEEDS_HUMAN` tickets prominently (this feeds the "replies we would not send" list).

Two-column grids that collapse to one column on narrow screens.

## 10. Data sources

| Need | Source |
|---|---|
| Ticket rows, actions, risk, replies, trace | `outputs/triage_results.csv` |
| Merchant records | `data/Buildathon_Student_Data_Pack.xlsx`, tab `P1_Merchants`, loaded by `src/triage/load.py` |
| KB articles | same workbook, tab `P1_KnowledgeBase` |
| Guardrail results | `outputs/guardrail_log.csv` |
| KB suggestions | `outputs/kb_insights.csv` |
| Spikes | `outputs/spikes.csv` |
| Thresholds, team names | `config/rules.yaml` |
| Agent actions | `outputs/agent_actions.csv` (new, append only) |

Cache loaders with `st.cache_data`. Never read the Data Pack inside page files directly. Go through `src/triage`.

## 11. Accessibility and responsiveness

- Use real buttons and links. Every icon-only button has a label.
- Never rely on colour alone. Risk, status and outcome always carry text.
- Touch targets at least 44px.
- Layout works from phone width: sidebar collapses, panels and grids stack, the queue table scrolls horizontally inside its card.

## 12. Build order

1. `app/theme.py` and `.streamlit/config.toml` (tokens, fonts, CSS, chips).
2. Shared data layer and definitions (section 5) with tests.
3. Ticket Workspace, including the three dialogs and the guardrail and send rules. Test the send-disabled rule for every Critical ticket.
4. Ticket Queue.
5. Overview.
6. Insights & Quality.
7. Update `README.md` (screens, how to run) and `docs/decisions_log.md` (the section 5 definitions and the removed screens). Update `docs/ai_usage_log.md`.

After each step, give Vasudev a short plain-language summary of what was built and why, as CLAUDE.md section 14 requires.

## 13. Acceptance checks

- Sidebar shows only Support Copilot, Overview, Ticket Queue, Insights & Quality. No Settings anywhere.
- No language or tone selectors in the Response Composer.
- Every number matches the output files. Spot check: the KPI cards on Overview equal the counts from `triage_results.csv`.
- For all 9 threat tickets, Approve & Send is disabled and the red banner shows.
- An edited reply that fails guardrails cannot be approved.
- KB dialog text is identical to the workbook text.
- No ticket ID, merchant ID or date is hardcoded in page logic.
- Pages render with no data errors when `outputs/` files are present, and show clear empty states when one is missing.
