"""Try It: paste a new ticket and run the real pipeline live. Results use the Ticket Workspace layout."""
from datetime import datetime

import streamlit as st

from common import page_header, show
from ticket_view import header_pills, workspace
from triage.config import load_config
from triage.llm import llm_available
from triage.lookup import merchants
from triage.pipeline import triage_ticket

cap = load_config()["llm"]["max_try_it_runs"]
st.session_state.setdefault("runs", 0)
live = llm_available()
page_header("Try It", ("Runs the real pipeline live with Claude. " if live else
                       "No API key found, so this runs the real pipeline with the keyword reader and templates. ")
            + f"Limit {cap} runs per session.")

with st.container(border=True, key="card_try"):
    msg = st.text_area("Merchant Message", height=110, placeholder="e.g. Mera settlement 3 din se nahi aaya, jaldi batao")
    c1, c2, c3 = st.columns([2, 1, 1], vertical_alignment="bottom")
    ms = merchants()
    mid = c1.selectbox("Merchant", ["(none)"] + sorted(ms), format_func=lambda m: m if m == "(none)"
                       else f"{m} · {ms[m]['business_name']}")
    channel = c2.selectbox("Channel", ["Chat", "Email", "WhatsApp"])
    run = c3.button("Run Triage", type="primary", disabled=not msg.strip(), use_container_width=True)

if run:
    if st.session_state.runs >= cap:
        st.error("Run limit reached for this session.")
        st.stop()
    st.session_state.runs += 1
    now = datetime.now()
    with st.spinner("Triaging"):
        res = triage_ticket("TRY-IT", msg.strip(), None if mid == "(none)" else mid, now, channel=channel,
                            created_at=now.strftime("%d %b %Y %H:%M"), offline=not live)
    st.session_state["try_result"] = (res.row, res.guard_log)

if "try_result" in st.session_state:
    row, guard = st.session_state["try_result"]
    show(header_pills(row))
    workspace(row, guard, key="try")
