"""Shared fixtures. Tests run the real pipeline in offline mode (deterministic, no API key needed)."""
import pytest

from triage.load import load_tickets
from triage.pipeline import triage_ticket


@pytest.fixture(scope="session")
def tickets():
    return load_tickets().set_index("ticket_id")


@pytest.fixture(scope="session")
def results(tickets):
    out = {}
    for tid, r in tickets.iterrows():
        res = triage_ticket(tid, r.merchant_message, r.merchant_id, r.created_dt.to_pydatetime(),
                            channel=r.channel, created_at=r.created_at, offline=True)
        out[tid] = res.row
    return out
