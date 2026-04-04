"""
Search Workers page — TODO.
"""

import streamlit as st


def render():
    st.title("🔍 Search Workers")
    st.info("🚧 **Coming soon** — The search UI is under development.")
    st.markdown(
        "In the meantime, you can use the API directly:  \n"
        "[Swagger Docs → GET /api/workers/stage/search](http://localhost:8000/docs#/workers/search_workers_api_workers_stage_search_get)"
    )
    # TODO: Build search form with same filter params as API, display results in a table
