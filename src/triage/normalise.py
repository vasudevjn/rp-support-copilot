"""Collapse ticket messages into message types by masking IDs, amounts and numbers."""
from __future__ import annotations

import re

import pandas as pd

_RULES = [
    (re.compile(r"\bpay_[A-Za-z0-9]+\b"), "<PAY_ID>"),
    (re.compile(r"\b(merchant id|merchant|mid)\s*M\d{4}\b", re.I), "<MID>"),
    (re.compile(r"\bM\d{4}\b"), "<MID>"),
    (re.compile(r"(rs\.?|₹)\s*[\d,]+", re.I), "<AMOUNT>"),
    (re.compile(r"\d[\d,]*(\.\d+)?"), "<N>"),
]


def normalise(message: str) -> str:
    text = message.strip()
    for pat, repl in _RULES:
        text = pat.sub(repl, text)
    text = re.sub(r"\s+", " ", text).strip(" .").lower()
    return text


def message_types(tickets: pd.DataFrame) -> pd.DataFrame:
    """One row per distinct normalised message, most frequent first."""
    t = tickets.assign(normalised=tickets["merchant_message"].map(normalise))
    g = (t.groupby("normalised")
           .agg(n_tickets=("ticket_id", "size"),
                example_ticket_id=("ticket_id", "first"),
                ticket_ids=("ticket_id", lambda s: " ".join(s)))
           .reset_index()
           .sort_values(["n_tickets", "example_ticket_id"], ascending=[False, True])
           .reset_index(drop=True))
    g.insert(0, "type_id", [f"MT-{i+1:02d}" for i in range(len(g))])
    return g
