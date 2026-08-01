import asyncio
import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from agent import scout


ROOT = Path(__file__).resolve().parent
TRACKER = ROOT / "applications.json"
load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="Scout · Job Hunt Co-pilot",
    page_icon="🧭",
    layout="centered",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 860px; padding-top: 3.5rem;}
    [data-testid="stForm"] {border: 1px solid #ccd8cf; padding: 1.4rem;}
    .scout-kicker {color: #1d6b52; font-size: .78rem; font-weight: 700;
        letter-spacing: .16em; text-transform: uppercase;}
    .scout-route {color: #52635a; font-size: .9rem; letter-spacing: .04em;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="scout-kicker">Agent Lab 01</div>', unsafe_allow_html=True)
st.title("Scout")
st.subheader("Turn a job post into a researched, resume-aware application.")
st.markdown(
    '<div class="scout-route">RESEARCH → MATCH → DRAFT → TRACK</div>',
    unsafe_allow_html=True,
)

with st.form("scout-form"):
    job = st.text_area(
        "Job description or posting URL",
        height=300,
        placeholder="Paste the full role description, or a public job-post URL...",
    )
    submitted = st.form_submit_button(
        "Scout this role",
        type="primary",
        use_container_width=True,
    )

if submitted:
    if not job.strip():
        st.warning("Paste a job description or URL first.")
    elif not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY is missing. Add it to .env or your deployment secrets.")
    else:
        try:
            with st.status("Scout is planning the application...", expanded=True) as status:
                report = asyncio.run(scout(job.strip(), trace=st.write))
                status.update(label="Application pack ready", state="complete")
            st.session_state["report"] = report
        except Exception as exc:
            st.error(f"Scout stopped: {exc}")

if report := st.session_state.get("report"):
    st.divider()
    st.markdown(report)

with st.expander("Application tracker", expanded=True):
    applications = json.loads(TRACKER.read_text(encoding="utf-8"))
    if applications:
        st.dataframe(applications, use_container_width=True, hide_index=True)
        st.download_button(
            "Download tracker",
            data=json.dumps(applications, indent=2, ensure_ascii=False),
            file_name="applications.json",
            mime="application/json",
        )
    else:
        st.caption("Completed applications will appear here.")

st.caption("Workshop demo: use a sanitized resume and your own API key.")
