"""Ticket Workspace: one ticket, the decision and why, the merchant record, and the drafted reply."""
import streamlit as st

from common import PAGES, csv, results, show
from ticket_view import header_pills, workspace

df = results()
ids = list(df.ticket_id)

# Which ticket: one opened from another page, else the URL (?t=T-0103), else the first.
incoming = st.session_state.pop("ticket", None)
if incoming in ids:
    st.session_state["ws_pick"] = incoming
elif st.session_state.get("ws_pick") not in ids:
    qp = st.query_params.get("t")
    st.session_state["ws_pick"] = qp if qp in ids else ids[0]

st.page_link(PAGES["queue"], label="Ticket Queue", icon=":material/arrow_back:")
head, pick = st.columns([3, 1], vertical_alignment="bottom")
with pick:
    tid = st.selectbox("Open Ticket", ids, key="ws_pick")
st.query_params["t"] = tid

r = df[df.ticket_id == tid].iloc[0].to_dict()
with head:
    show(header_pills(r))

g = csv("guardrail_log.csv")
guard = g[g.ticket_id == tid].to_dict("records") if g is not None else []
workspace(r, guard, key=tid)
