
import os
import json
import streamlit as st
import pandas as pd
from groq import Groq
from dotenv import load_dotenv

from core.data_loader import (
    load_regional_timeseries,
    load_interaction_results,
    load_district_results,
    load_trend_results,
)

from config import APP_NAME, ANALYSIS_START, ANALYSIS_END

from components.theme import inject_theme, page_header, section_header, info_banner, footer
from components.sidebar import render_sidebar

load_dotenv()

# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="AI Scientist | EARTHPULSE-X",
    page_icon="🧠",
    layout="wide",
)

inject_theme()
render_sidebar()


# --------------------------------------------------
# DATA LOADING
# --------------------------------------------------

@st.cache_data
def load_scientific_data():
    regional = load_regional_timeseries()
    interactions = load_interaction_results()
    districts = load_district_results()

    # Load precomputed autocorrelation-adjusted trend results
    # so the AI Scientist has full statistical context for
    # trend-specific questions (fixing the gap identified in review)
    try:
        trends = load_trend_results()
    except Exception:
        trends = pd.DataFrame()

    return regional, interactions, districts, trends


try:
    regional, interactions, districts, trends = load_scientific_data()

except Exception as error:
    st.error(f"Could not load research data: {error}")
    st.stop()


# --------------------------------------------------
# DATA PREPARATION
# --------------------------------------------------

VARIABLES = {
    "Land Surface Temperature": "lst_strict_mean",
    "Vegetation Index": "ndvi_strict_mean",
    "Soil Moisture (AM)": "smap_am_strict_mean",
    "Soil Moisture (PM)": "smap_pm_strict_mean",
    "Precipitation": "gpm_monthly_precipitation_mean",
}


def safe_number(value, digits=3):
    if pd.isna(value):
        return "N/A"

    return f"{value:,.{digits}f}"


def build_research_context():
    """Build a compact context using only actual research outputs."""

    latest = regional.iloc[-1]

    regional_summary = {
        "analysis_period": f"{ANALYSIS_START} to {ANALYSIS_END}",
        "number_of_monthly_records": len(regional),
        "latest_month": str(latest["month"]),
        "latest_observations": {},
    }

    for label, column in VARIABLES.items():
        if column in regional.columns:
            regional_summary["latest_observations"][label] = (
                safe_number(latest[column], 4)
            )

    # District anomaly results
    district_columns = [
        "district_name",
        "valid_pixels",
        "total_anomaly_pixels",
        "anomaly_pixel_percentage",
        "mean_precipitation_mm",
        "mean_absolute_robust_z",
        "maximum_absolute_robust_z",
    ]

    available_district_columns = [
        col for col in district_columns if col in districts.columns
    ]

    district_summary = districts[
        available_district_columns
    ].sort_values(
        "anomaly_pixel_percentage",
        ascending=False,
    ).to_dict(orient="records")

    # Significant interaction results
    significant = interactions.copy()

    if "fdr_significant" in significant.columns:
        significant = significant[
            significant["fdr_significant"].astype(str).str.lower()
            .isin(["true", "1"])
        ]

    if "fdr_q_value" in significant.columns:
        significant = significant.sort_values("fdr_q_value")

    interaction_columns = [
        "variable_x",
        "variable_y",
        "lag_months",
        "sample_size",
        "spearman_rho",
        "p_value",
        "fdr_q_value",
        "fdr_significant",
    ]

    available_interaction_columns = [
        col for col in interaction_columns if col in significant.columns
    ]

    interaction_summary = significant[
        available_interaction_columns
    ].head(20).to_dict(orient="records")

    # Precomputed autocorrelation-adjusted trend results
    trend_summary = []
    if not trends.empty:
        trend_cols = [
            "variable", "modified_mk_trend", "modified_mk_tau",
            "fdr_adjusted_p_value_modified", "fdr_significant",
            "trend_slope_per_year", "lag1_autocorrelation",
        ]
        available_trend_cols = [
            c for c in trend_cols if c in trends.columns
        ]
        if available_trend_cols:
            trend_summary = trends[available_trend_cols].to_dict(
                orient="records"
            )

    return {
        "regional_summary": regional_summary,
        "district_anomaly_results": district_summary,
        "significant_interactions": interaction_summary,
        "trend_results": trend_summary,
    }


research_context = build_research_context()


# --------------------------------------------------
# GROQ CONFIGURATION
# --------------------------------------------------

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b"
)

SYSTEM_PROMPT = """
You are the AI Scientific Research Assistant of EARTHPULSE-X.

EARTHPULSE-X is a physics-aware, uncertainty-guided Earth system
intelligence research project focused on Uttarakhand, India.

Your task is to interpret the research data supplied to you.

STRICT SCIENTIFIC RULES:

1. Use only the supplied research context for project-specific facts.
2. Never invent measurements, trends, locations, events or statistics.
3. Clearly distinguish observed results from interpretations and hypotheses.
4. Correlation does not establish causation.
5. Statistical anomalies are NOT confirmed floods, landslides or disasters.
6. An anomaly score does not independently establish physical damage.
7. Low observation coverage is a data-availability limitation.
   It must not automatically be described as measurement uncertainty.
8. Do not claim independent physical validation unless the data supports it.
9. Do not invent elevation, temperature, rainfall or vegetation trends.
10. If information is unavailable, explicitly say so.
11. Explain scientific concepts in clear, accessible language.
12. When discussing interaction results, mention the lag, sample size,
    correlation coefficient and FDR significance where available.
13. Never describe correlation as proof of a physical mechanism.
14. Be transparent about limitations and missing evidence.

For every scientific interpretation, structure the answer as:

### Observation
What the supplied data actually shows.

### Interpretation
What this result may indicate, without claiming causation.

### Limitations
What cannot be concluded from the available evidence.

### Further Investigation
What additional analysis or validation could strengthen the finding.

You are a scientific assistant, not a general-purpose chatbot.
"""


def get_groq_client():
    if not GROQ_API_KEY:
        return None

    return Groq(api_key=GROQ_API_KEY)


def ask_ai(question, chat_history=None):
    client = get_groq_client()

    if client is None:
        raise ValueError(
            "GROQ_API_KEY not found. Please configure it in your .env file."
        )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT
            + "\n\nACTUAL RESEARCH CONTEXT:\n"
            + json.dumps(research_context, indent=2, default=str),
        }
    ]

    if chat_history:
        messages.extend(chat_history[-8:])

    messages.append({
        "role": "user",
        "content": question,
    })

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.2,
        max_completion_tokens=2500,
    )

    return response.choices[0].message.content


# --------------------------------------------------
# HEADER
# --------------------------------------------------

page_header(
    "AI SCIENTIST",
    "Evidence-Grounded Scientific Reasoning & Earth System Intelligence",
    "🧠",
)

st.markdown(
    "An evidence-grounded AI research assistant that interprets "
    "EARTHPULSE-X observations, district anomalies and environmental "
    "interactions."
)

st.divider()


# --------------------------------------------------
# SYSTEM STATUS
# --------------------------------------------------

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Monthly Records", len(regional))

with col2:
    st.metric("Trend Variables", len(trends) if not trends.empty else 0)

with col3:
    st.metric("Districts", len(districts))

with col4:
    st.metric("Interaction Records", len(interactions))

with col5:
    st.metric(
        "FDR Significant",
        int(
            interactions["fdr_significant"].astype(str).str.lower()
            .isin(["true", "1"]).sum()
        ) if "fdr_significant" in interactions.columns else 0
    )

if GROQ_API_KEY:
    st.success(f"AI Engine Configured · {GROQ_MODEL}")
else:
    st.warning(
        "Groq API key is not configured. Add GROQ_API_KEY to your .env file."
    )

st.divider()


# --------------------------------------------------
# RESEARCH CONTEXT EXPLORER
# --------------------------------------------------

section_header("Research Knowledge Base", "🔬")

with st.expander("View the data available to the AI Scientist"):

    tab1, tab2, tab3, tab4 = st.tabs([
        "Regional Observations",
        "Trend Results",
        "District Anomalies",
        "Environmental Interactions",
    ])

    with tab1:
        st.markdown("**Latest regional observations**")
        st.json(research_context["regional_summary"])

    with tab2:
        st.markdown("**Autocorrelation-adjusted trend results**")
        st.caption(
            "Modified Mann-Kendall (Hamed & Rao 1998) with FDR correction. "
            "These results are now included in the AI Scientist's context."
        )
        if not trends.empty:
            st.dataframe(trends, use_container_width=True, hide_index=True)
        else:
            st.info("Trend results file not found.")

    with tab3:
        st.markdown("**District-wise anomaly intelligence**")
        st.dataframe(
            districts,
            use_container_width=True,
            hide_index=True,
        )

    with tab4:
        st.markdown("**FDR-significant interaction results**")
        st.dataframe(
            interactions[
                interactions["fdr_significant"].astype(str).str.lower()
                .isin(["true", "1"])
            ] if "fdr_significant" in interactions.columns
            else interactions,
            use_container_width=True,
            hide_index=True,
        )


# --------------------------------------------------
# QUICK SCIENTIFIC QUESTIONS
# --------------------------------------------------

section_header("Ask Scientific Questions", "💡")

quick_questions = {
    "Regional Environmental Summary":
        "Give me a scientific summary of the latest regional observations "
        "across LST, NDVI, soil moisture and precipitation.",

    "Trend Analysis Summary":
        "Analyze the autocorrelation-adjusted trend results for all 5 "
        "environmental variables. Which are significantly changing? "
        "State direction, Sen's slope, FDR-adjusted p-values, and lag-1 "
        "autocorrelation. Explain why autocorrelation correction matters.",

    "District Anomaly Analysis":
        "Analyze the August 2025 district-wise precipitation anomaly results. "
        "Identify the strongest observed patterns and explain the limitations.",

    "Environmental Interactions":
        "Explain the strongest FDR-significant relationships between "
        "environmental variables. Discuss their correlations and time lags.",

    "Data Quality Assessment":
        "Evaluate the observation coverage and data quality limitations "
        "of the EARTHPULSE-X research dataset.",

    "Scientific Research Report":
        "Prepare a structured scientific research report summarizing "
        "the regional observations, trend results, district anomalies, "
        "environmental interactions and research limitations.",
}

question_columns = st.columns(2)

for index, (label, question) in enumerate(quick_questions.items()):
    with question_columns[index % 2]:
        if st.button(
            label,
            use_container_width=True,
            key=f"quick_{index}",
        ):
            st.session_state["pending_ai_question"] = question


# --------------------------------------------------
# AI CHAT INTERFACE
# --------------------------------------------------

st.divider()

st.header("💬 Chat with AI Scientist")

if "ai_messages" not in st.session_state:
    st.session_state.ai_messages = []

if "pending_ai_question" not in st.session_state:
    st.session_state.pending_ai_question = None


# Display previous conversation
for message in st.session_state.ai_messages:

    with st.chat_message(message["role"]):
        st.markdown(message["content"])


# Handle quick question or normal chat input
user_question = st.chat_input(
    "Ask about environmental trends, anomalies, interactions..."
)

if st.session_state.pending_ai_question:
    user_question = st.session_state.pending_ai_question
    st.session_state.pending_ai_question = None


if user_question:

    st.session_state.ai_messages.append({
        "role": "user",
        "content": user_question,
    })

    with st.chat_message("user"):
        st.markdown(user_question)

    with st.chat_message("assistant"):

        with st.spinner("Analyzing research evidence..."):

            try:
                previous_history = [
                    message for message in st.session_state.ai_messages[:-1]
                ]

                answer = ask_ai(
                    user_question,
                    previous_history,
                )

                st.markdown(answer)

                st.session_state.ai_messages.append({
                    "role": "assistant",
                    "content": answer,
                })

            except Exception as error:
                st.error(f"AI Scientist Error: {error}")

                st.info(
                    "Check your Groq API key, model availability and "
                    "internet connection."
                )

    st.rerun()


# --------------------------------------------------
# CHAT CONTROLS
# --------------------------------------------------

col_a, col_b = st.columns([1, 5])

with col_a:
    if st.button("🗑️ Clear Chat", use_container_width=True):
        st.session_state.ai_messages = []
        st.rerun()

with col_b:
    st.caption(
        "AI-generated interpretations are research assistance, "
        "not independent scientific validation."
    )


# --------------------------------------------------
# SCIENTIFIC SAFETY NOTICE
# --------------------------------------------------

st.divider()

info_banner(
    "**Scientific Integrity Notice** — AI Scientist uses existing EARTHPULSE-X research outputs to generate "
    "evidence-grounded explanations. AI-generated interpretations should be reviewed against the underlying "
    "observations and statistical methods. Correlation does not imply causation. Statistical anomalies are not "
    "confirmed natural disasters.",
    kind="info",
)

footer()
