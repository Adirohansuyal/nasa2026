"""
UG-ESI Contribution 4: Evidence-Grounded Scientific Reasoning Agent
====================================================================
Centralized AI reasoning layer for EARTHPULSE-X.

All explanations must be traceable to actual data.
The LLM explains findings; statistical engines establish them.

Rules enforced in every prompt:
  - No invented measurements, trends, or events
  - Correlation ≠ causation
  - Uncertainty and limitations must be explicit
  - Direct, factual, bullet-point style (no storytelling)
"""

import json
import os
from groq import Groq

# -----------------------------------------
# Groq client (hardcoded key; remove before publish)
# -----------------------------------------

_GROQ_API_KEY = os.getenv("GROQ_API_KEY")

_GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def get_client() -> Groq:
    return Groq(api_key=_GROQ_API_KEY)


def _call(
    prompt: str,
    max_tokens: int = 700,
    temperature: float = 0.3,
) -> str:
    """Low-level Groq call. Returns response text."""
    client = get_client()
    response = client.chat.completions.create(
        model=_GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


# -----------------------------------------
# Base instruction injected into every prompt
# -----------------------------------------

_BASE_RULES = """
STRICT RULES — follow these for every response:
1. Use ONLY the supplied data for specific numbers and findings.
2. Never invent measurements, trends, or events.
3. Correlation does not establish causation — never imply it does.
4. Distinguish observed results from interpretations.
5. State data quality and coverage limitations explicitly.
6. No storytelling, no warm intros. Be direct and factual.
7. Use short bullet points. Include actual numbers.
8. End with a one-line VERDICT on what this means.
"""


# -----------------------------------------
# 1. Variable Selection Explainer
# -----------------------------------------

def explain_variable_selection(
    selection_summary: str,
    objective: str,
) -> str:
    prompt = f"""You are a data analyst for EARTHPULSE-X, an Earth science intelligence platform.

{_BASE_RULES}

A user selected objective: "{objective}"
The adaptive variable selection engine ranked the available environmental variables.

Selection results:
{selection_summary}

Explain:
- Which variables were ranked highest and why (use the actual scores)
- Which variables were ranked lower and what that means for analysis
- Whether the selected set covers the right combination for this objective
- One specific limitation of this variable set for the stated objective

Short bullets. Actual scores. No jargon."""

    return _call(prompt, max_tokens=500)


# -----------------------------------------
# 2. Trend Analysis Explainer
# -----------------------------------------

def explain_trend(
    variable_label: str,
    trend_report: dict,
    unit: str = "",
) -> str:
    # Use modified Mann-Kendall (autocorrelation-adjusted) when available,
    # falling back to basic Mann-Kendall for backward compatibility
    mk = trend_report.get("modified_mann_kendall", {}) or \
         trend_report.get("mann_kendall", {})
    ols = trend_report.get("ols", {})
    ss = trend_report.get("sens_slope", {})
    cp = trend_report.get("change_points", {})
    n_months = trend_report.get("n_months", "?")
    annual_slope = trend_report.get("annualised_sens_slope", "?")

    change_point_text = "None detected"
    cp_list = cp.get("change_points", [])
    if cp_list:
        top_cp = cp_list[0]
        change_point_text = (
            f"{top_cp.get('direction', '?')} around "
            f"{str(top_cp.get('index', '?'))[:7]}, "
            f"CUSUM value: {top_cp.get('cusum_value', '?'):.2f}"
        )

    # Include autocorrelation info if available
    autocorr_info = ""
    if "lag1_autocorrelation" in mk:
        autocorr_info = (
            f"\nLag-1 autocorrelation: {mk.get('lag1_autocorrelation', '?'):.3f} "
            f"(effective N: {mk.get('effective_n', '?')})"
        )

    method_name = mk.get("method", "Mann-Kendall")

    summary = f"""Variable: {variable_label} ({unit})
Analysis period: {n_months} months
Trend method: {method_name}
Direction: {mk.get('direction','?')}, tau={mk.get('tau','?'):.3f}, p={mk.get('p_value','?'):.4g}, significant={mk.get('significant','?')}
OLS slope: {ols.get('slope','?'):.4g} per month, R²={ols.get('r_squared','?'):.3f}, p={ols.get('p_value','?'):.4g}
Sen's slope: {ss.get('slope','?'):.4g} per month ({annual_slope:.4g} per year if numeric)
Most notable change point: {change_point_text}{autocorr_info}"""

    prompt = f"""You are a data analyst for EARTHPULSE-X.

{_BASE_RULES}

A statistical trend analysis was run on this environmental variable.

Results:
{summary}

Explain:
- Is there a significant trend? State direction, strength (tau value), and p-value directly
- How much is this variable changing per year (use Sen's slope, not OLS)
- Were any sudden shifts detected? When and in which direction?
- How reliable is this trend — is the R² high or low, is the sample large enough?
- VERDICT: one sentence on what this trend means for Uttarakhand

No storytelling. Bullets. Numbers."""

    return _call(prompt, max_tokens=500)


# -----------------------------------------
# 3. Interaction Graph Explainer
# -----------------------------------------

def explain_interaction_graph(
    graph_summary: str,
    variables_used: list,
    lag_range: str = "0–3 months",
) -> str:
    prompt = f"""You are a data analyst for EARTHPULSE-X.

{_BASE_RULES}

An uncertainty-guided interaction graph was computed between these environmental variables: {', '.join(variables_used)}.
Temporal lags tested: {lag_range}.
Each relationship was tested with Spearman correlation, FDR-corrected for multiple testing, and assigned a confidence score based on effect size, statistical certainty, data volume, and temporal stability.

Graph results:
{graph_summary}

Explain:
- Which relationships are the strongest (actual rho values)
- For each strong relationship: what it means in plain terms (e.g. "more rain → wetter soil 1 month later")
- Which relationships have highest confidence scores and why
- Are there any surprising or unexpected relationships?
- VERDICT: what does this interaction network tell us about how Uttarakhand's environment works?

Bullets. Numbers. No jargon. No "Spearman" or "FDR" — say "strength" and "statistical confidence"."""

    return _call(prompt, max_tokens=600)


# -----------------------------------------
# 4. Full UG-ESI Research Report
# -----------------------------------------

def generate_research_report(
    objective: str,
    variable_selection_summary: str,
    trend_summaries: list,
    interaction_summary: str,
    coverage_notes: str = "",
) -> str:
    """
    Generate a structured evidence-grounded research report
    covering all four UG-ESI contributions.
    """

    trends_text = "\n".join(
        f"  - {t}" for t in trend_summaries
    )

    prompt = f"""You are a scientific AI assistant for EARTHPULSE-X.

{_BASE_RULES}

Generate a structured research report for the following analysis.

RESEARCH OBJECTIVE: {objective}
STUDY REGION: Uttarakhand, India
ANALYSIS PERIOD: 2015–2025

--- ADAPTIVE VARIABLE SELECTION ---
{variable_selection_summary}

--- MULTI-SCALE TREND FINDINGS ---
{trends_text}

--- INTERACTION GRAPH FINDINGS ---
{interaction_summary}

--- DATA QUALITY NOTES ---
{coverage_notes if coverage_notes else "No coverage limitations noted."}

Structure your report as:
1. KEY FINDINGS — bullet points with actual numbers
2. VARIABLE RELATIONSHIPS — which variables move together and when
3. DATA RELIABILITY — what can and cannot be concluded from this data
4. LIMITATIONS — gaps, uncertainties, and missing evidence
5. RESEARCH VERDICT — one paragraph maximum, evidence-grounded

No invented facts. No causation claims. Direct language. Traceable to the data above."""

    return _call(prompt, max_tokens=900, temperature=0.2)


# -----------------------------------------
# 5. Anomaly Digest Explainer
# -----------------------------------------

def explain_anomaly_digest(
    district_rows: list,
    top_n: int = 3,
) -> str:
    """
    Explain district-level anomaly results for top_n districts.
    """
    if not district_rows:
        return "No district anomaly data available."

    sorted_rows = sorted(
        district_rows,
        key=lambda x: x.get("anomaly_pixel_percentage", 0),
        reverse=True,
    )[:top_n]

    lines = [
        f"District: {r.get('district_name','?')}, "
        f"high-anomaly area: {r.get('anomaly_pixel_percentage','?'):.1f}%, "
        f"mean precipitation: {r.get('mean_precipitation_mm','?'):.1f} mm, "
        f"mean |robust Z|: {r.get('mean_absolute_robust_z','?'):.2f}, "
        f"max |robust Z|: {r.get('maximum_absolute_robust_z','?'):.2f}"
        for r in sorted_rows
    ]

    data_text = "\n".join(lines)

    prompt = f"""You are a data analyst for EARTHPULSE-X.

{_BASE_RULES}

The following districts in Uttarakhand had the highest precipitation anomaly in August 2025 compared to the historical baseline (August 2015–2024). Anomalies are measured using a robust Z-score (threshold: +3.5).

Data:
{data_text}

Explain:
- Which districts had the most unusual precipitation and by how much (use the % and Z-score)
- What a high robust Z-score means in plain terms
- Whether these anomaly levels are remarkable given the baseline
- IMPORTANT CAVEAT: state clearly that high precipitation anomaly does NOT automatically mean flooding or disaster
- VERDICT: what these numbers tell us about August 2025 precipitation in Uttarakhand

Bullets. Numbers. No invented consequences."""

    return _call(prompt, max_tokens=500)
