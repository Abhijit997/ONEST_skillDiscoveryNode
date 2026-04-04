"""
ONEST Skill Discovery Node — Streamlit UI entry point.
Provides navigation to Insert Workers and Search Workers pages.
"""

import streamlit as st

st.set_page_config(
    page_title="ONEST Skill Discovery Node",
    page_icon="🔧",
    layout="wide",
)


# ── Sidebar navigation ──
pages = {
    "🏠 Home": "home",
    "➕ Insert Workers": "insert",
    "🔍 Search Workers": "search",
    "� Chat Simulator": "chat",
}

selection = st.sidebar.radio("Navigate", list(pages.keys()))
page = pages[selection]


# ── Home ──
if page == "home":
    st.title("🔧 ONEST Skill Discovery Node")
    st.markdown(
        """
        Welcome to the **Blue-Collar Worker Discovery** management console.

        Use the sidebar to navigate:
        - **Insert Workers** — Add workers manually or upload CSV/Excel
        - **Search Workers** — Query and filter the worker stage table
        - **Chat Simulator** — Phone verification chat with workers

        ---
        **Backend:** FastAPI on `http://localhost:8000`
        ([Swagger Docs](http://localhost:8000/docs))
        """
    )

# ── Insert Workers ──
elif page == "insert":
    from ui.views.insert_workers import render
    render()

# ── Search Workers ──
elif page == "search":
    from ui.views.search_workers import render
    render()

# ── Chat Simulator ──
elif page == "chat":
    from ui.views.chat_simulator import render
    render()
