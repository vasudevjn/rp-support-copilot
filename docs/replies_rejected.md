# Replies rejected in human review

Drafts I would not send after reading them, with the reason. The pipeline reads this table
(`src/triage/review.py`) and adds every row to `outputs/replies_not_sent.csv`, next to the automatic blocks
(threat drafts and guardrail failures).

Status:
- `open`: the current draft is still rejected. The pipeline sets that ticket to `do_not_send`.
- `fixed`: the cause was fixed in a template, prompt or rule. The row stays here as a record.

Rows marked "found with Claude Code" came from a review pass on 09 Nov 2026. Vasudev to confirm each one.

| Tickets | Rejected draft (excerpt) | Reason | Status |
|---|---|---|---|
| T-0021 T-0027 T-0030 T-0031 T-0060 T-0115 T-0138 | "I'm sorry for the frustration this has caused..." | Apology in a threat holding reply. Under KB-15, Legal may read it as admitting fault. The LLM polisher added it for angry tone and the guardrail missed it. Fix: threat replies skip the polisher; apology words banned in threat replies. | fixed |
| T-0002 T-0021 T-0027 T-0030 T-0031 T-0060 T-0078 T-0115 T-0138 | "...the right specialist team, who will review it and contact you directly." | A commitment in a threat reply. KB-15 says no commitments. Fix: threat template now says only that the message was shared with the right team for review. (Found with Claude Code.) | fixed |
| T-0003 | "They will get in touch with you to discuss it." | Fee waiver request. "Discuss it" can read as the waiver being negotiable, which KB-09 says Customer Success cannot promise. Fix: reply now says only that the request went to the Account Manager for review. (Found with Claude Code.) | fixed |
| T-0052 | "I understand how stressful this is, and I'm sorry for the trouble. SIGNATURE_MISMATCH means..." | The same stock apology opened every frustrated reply, even a technical one. It reads as boilerplate, and an apology can imply fault. Fix: the opening line now depends on the category (for example "I know integration errors hold up your work.") and has no apology. (Found with Claude Code.) | fixed |
| T-0018 T-0032 T-0034 T-0044 T-0107 T-0111 T-0131 T-0150 | "...and I'm sorry for the worry this causes." | After the stock apology was removed from the templates, the LLM polisher added one back on re-polish. Fix: a guardrail now fails any reply with an apology; all 8 were regenerated once and passed. (Found with Claude Code.) | fixed |
