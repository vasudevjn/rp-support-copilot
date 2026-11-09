"""Dashboard entry point and router. Run: streamlit run app/streamlit_app.py

Pages live in app/views/. The sidebar is drawn by common.sidebar() so it matches the design mockup;
Ticket Workspace is reached from the queue, not the sidebar.
"""
import streamlit as st

import common

st.set_page_config(page_title="Support Copilot", page_icon=common.FAVICON_SVG, layout="wide",
                   initial_sidebar_state="auto")   # open on desktop, collapsed on phones

common.PAGES.update({
    "overview": st.Page("views/overview.py", title="Overview", url_path="overview", default=True),
    "queue": st.Page("views/queue.py", title="Ticket Queue", url_path="queue"),
    "workspace": st.Page("views/workspace.py", title="Ticket Workspace", url_path="workspace"),
    "insights": st.Page("views/insights.py", title="Insights & Quality", url_path="insights"),
    "try_it": st.Page("views/try_it.py", title="Try It", url_path="try-it"),
})

nav = st.navigation(list(common.PAGES.values()), position="hidden")
common.inject_css()
common.sidebar()
nav.run()
