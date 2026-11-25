import streamlit as st

st.set_page_config(
    page_title="Uttarakhand land-cover research",
    page_icon=":material/forest:",
    layout="wide",
)

active_page = st.session_state.get("research_active_page", "distribution")

pages = [
    st.Page(
        "views/distribution.py",
        title="Land-cover distribution",
        icon=":material/landscape:",
        url_path="land-cover",
        default=active_page == "distribution",
        help="Explore annual class areas and district shares, or compare a land-cover class across Uttarakhand.",
    ),
    st.Page(
        "views/trends.py",
        title="District trends",
        icon=":material/trending_up:",
        url_path="district-trends",
        default=active_page == "trends",
        help="Compare yearly class trends by district and statewide, including the largest estimated increases and decreases.",
    ),
]

page = st.navigation(pages, position="top")
st.session_state["research_active_page"] = (
    "trends" if page.title == "District trends" else "distribution"
)
page.run()
