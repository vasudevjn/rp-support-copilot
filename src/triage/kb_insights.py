"""Which KB articles should be improved? (stretch goal)

Signals per article, all counted from the triage output:
- no_kb_match: tickets where no article covered the request (escalated as a gap)
- ask_info: tickets that needed more information before acting
- ambiguous: tickets that hit a rule where the KB was silent or ambiguous (config kb_ambiguity)
"""
from __future__ import annotations

import pandas as pd

from .config import OUTPUTS, load_config
from .load import load_kb


def article_stats(df: pd.DataFrame) -> pd.DataFrame:
    kb = load_kb()
    amb = load_config()["kb_ambiguity"]
    rows = {k: {"kb_id": k, "topic": v["topic"], "tickets_citing": 0, "no_kb_match": 0, "ask_info": 0,
                "ambiguous": 0, "notes": set(), "example_tickets": []} for k, v in kb.items()}
    for r in df.itertuples():
        cited = [k.strip() for k in r.kb_ids.split(",") if k.strip()]
        for k in cited:
            rows[k]["tickets_citing"] += 1
        if r.sub_case in amb:
            k = amb[r.sub_case]["kb"]
            rows[k]["ambiguous"] += 1
            rows[k]["notes"].add(amb[r.sub_case]["note"])
            if len(rows[k]["example_tickets"]) < 5:
                rows[k]["example_tickets"].append(r.ticket_id)
            if not cited:
                rows[k]["no_kb_match"] += 1
        if r.action == "ask_info":
            for k in cited or ["KB-16"]:
                rows[k]["ask_info"] += 1
    out = pd.DataFrame(rows.values())
    out["notes"] = out["notes"].map(lambda s: " | ".join(sorted(s)))
    out["example_tickets"] = out["example_tickets"].map(" ".join)
    out["improvement_score"] = out.no_kb_match * 2 + out.ambiguous + out.ask_info
    return out.sort_values(["improvement_score", "kb_id"], ascending=[False, True]).reset_index(drop=True)


def no_kb_tickets(df: pd.DataFrame) -> pd.DataFrame:
    return df[df.kb_ids.str.strip() == ""][["ticket_id", "category", "sub_case", "merchant_message"]]


def write(df: pd.DataFrame) -> None:
    article_stats(df).to_csv(OUTPUTS / "kb_insights.csv", index=False)
    no_kb_tickets(df).to_csv(OUTPUTS / "kb_gaps.csv", index=False)
