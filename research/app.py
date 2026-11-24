import streamlit as st

st.set_page_config(
    page_title="Uttarakhand land-cover research",
    page_icon=":material/forest:",
    layout="wide",
)

pages = [
    st.Page(
        "views/distribution.py",
        title="Land-cover distribution",
        icon=":material/landscape:",
        default=True,
        help="Explore annual class areas and district shares, or compare a land-cover class across Uttarakhand.",
    ),
    st.Page(
        "views/trends.py",
        title="District trends",
        icon=":material/trending_up:",
        help="Compare yearly class trends by district and statewide, including the largest estimated increases and decreases.",
    ),
]

page = st.navigation(pages, position="top")
page.run()
