"""EARTHPULSE-X application entry point and page navigation."""

import streamlit as st


st.set_page_config(
    page_title="EARTHPULSE-X",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded",
)


pages = [
    st.Page("pages/01_Mission_Control.py", title="Mission Control", icon="🛰️", default=True),
    st.Page("pages/02_Earth_Observation.py", title="Earth Observation", icon="🌍"),
    st.Page("pages/03_Trend_Detective.py", title="Trend Detective", icon="📈"),
    st.Page("pages/04_Anomaly_Intelligence.py", title="Anomaly Intelligence", icon="⚠️"),
    st.Page("pages/05_Interaction_Network.py", title="Interaction Network", icon="🕸️"),
    st.Page("pages/06_Physics_Uncertainty.py", title="Physics & Uncertainty", icon="⚛️"),
    st.Page("pages/07_AI_Scientist.py", title="AI Scientist", icon="🤖"),
    st.Page("pages/08_Predictive_Intelligence.py", title="Predictive Intelligence", icon="🔮"),
    st.Page("pages/09_Early_Warning_System.py", title="Early Warning System", icon="🚨"),
    st.Page("pages/10_Causal_Discovery.py",    title="Causal Discovery",     icon="🔗"),
]

selected_page = st.navigation(pages, position="sidebar")
selected_page.run()
