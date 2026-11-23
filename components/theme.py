"""
Premium UI Theme & Reusable Components for EARTHPULSE-X
========================================================
All pages import from here for consistent premium styling.
"""

import streamlit as st
import re


# ──────────────────────────────────────────────────────────────
# 1. CSS THEME — Inject once per page
# ──────────────────────────────────────────────────────────────

_PREMIUM_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Urbanist:wght@400;500;600;700;800&display=swap" rel="stylesheet">

<style>
/* ─── ROOT ─── */
:root {
  --bg-deep: #060B14;
  --bg-base: #0A1020;
  --bg-card: #0F1A2E;
  --bg-card-hover: #132039;
  --border: #1E2D4A;
  --border-active: #2A3F5F;
  --accent: #35C9D0;
  --accent-glow: rgba(53, 201, 208, 0.15);
  --accent-2: #6C8EE6;
  --accent-3: #E9A34B;
  --text-primary: #F1F5FC;
  --text-secondary: #AAB8CC;
  --text-muted: #6B7B91;
  --green: #31C48D;
  --red: #EF6461;
  --radius: 14px;
  --radius-sm: 8px;
  --shadow: 0 4px 20px rgba(0,0,0,0.4);
  --transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

/* ─── APP BACKGROUND ─── */
.stApp {
  background: var(--bg-deep);
  background-image:
    radial-gradient(ellipse 80% 50% at 50% -10%, rgba(53,201,208,0.06), transparent),
    radial-gradient(ellipse 60% 40% at 80% 100%, rgba(108,142,230,0.04), transparent);
  color: var(--text-primary);
  font-family: 'Urbanist', sans-serif;
  font-feature-settings: 'cv11', 'ss01';
  letter-spacing: -0.01em;
}

/* Keep the same typeface across Streamlit widgets and rendered text. */
.stApp input, .stApp textarea, .stApp select, .stApp button,
.stApp [role="combobox"], .stApp [role="option"],
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMetricLabel"], .stApp [data-testid="stMetricValue"],
.stApp [data-testid="stCaptionContainer"],
.stApp [data-testid="stDataFrame"], .stApp [data-testid="stTable"] {
  font-family: 'Urbanist', sans-serif !important;
}

/* ─── AI EXPLANATION TYPOGRAPHY ─── */
.st-key-ai-regional-trend-response [data-testid="stMarkdownContainer"],
.st-key-ai-regional-trend-response [data-testid="stMarkdownContainer"] *,
.st-key-ai-regional-trend-response [data-testid="stMarkdownContainer"] p,
.st-key-ai-regional-trend-response [data-testid="stMarkdownContainer"] li,
.st-key-ai-regional-trend-response [data-testid="stCaptionContainer"],
.st-key-ai-district-anomaly-response [data-testid="stMarkdownContainer"],
.st-key-ai-district-anomaly-response [data-testid="stMarkdownContainer"] *,
.st-key-ai-district-anomaly-response [data-testid="stMarkdownContainer"] p,
.st-key-ai-district-anomaly-response [data-testid="stMarkdownContainer"] li,
.st-key-ai-district-anomaly-response [data-testid="stCaptionContainer"],
.st-key-ai-district-cycle-response [data-testid="stMarkdownContainer"],
.st-key-ai-district-cycle-response [data-testid="stMarkdownContainer"] *,
.st-key-ai-district-cycle-response [data-testid="stMarkdownContainer"] p,
.st-key-ai-district-cycle-response [data-testid="stMarkdownContainer"] li,
.st-key-ai-district-cycle-response [data-testid="stCaptionContainer"],
.st-key-ai-heatmap-response [data-testid="stMarkdownContainer"],
.st-key-ai-heatmap-response [data-testid="stMarkdownContainer"] *,
.st-key-ai-heatmap-response [data-testid="stMarkdownContainer"] p,
.st-key-ai-heatmap-response [data-testid="stMarkdownContainer"] li,
.st-key-ai-heatmap-response [data-testid="stCaptionContainer"] {
  font-family: 'Urbanist', sans-serif !important;
  line-height: 1.65;
  letter-spacing: 0;
}
.st-key-ai-regional-trend-response [data-testid="stMarkdownContainer"] li,
.st-key-ai-district-anomaly-response [data-testid="stMarkdownContainer"] li,
.st-key-ai-district-cycle-response [data-testid="stMarkdownContainer"] li,
.st-key-ai-heatmap-response [data-testid="stMarkdownContainer"] li {
  margin-bottom: 0.35rem;
}
.st-key-ai-regional-trend-response [data-testid="stVerticalBlockBorderWrapper"],
.st-key-ai-district-anomaly-response [data-testid="stVerticalBlockBorderWrapper"],
.st-key-ai-district-cycle-response [data-testid="stVerticalBlockBorderWrapper"],
.st-key-ai-heatmap-response [data-testid="stVerticalBlockBorderWrapper"] {
  background: linear-gradient(145deg, rgba(53,201,208,0.055), rgba(15,26,46,0.82)) !important;
  border-color: rgba(53,201,208,0.22) !important;
  border-radius: 14px !important;
  box-shadow: 0 5px 18px rgba(0,0,0,0.16);
}
.st-key-ai-regional-trend-response [data-testid="stCaptionContainer"],
.st-key-ai-district-anomaly-response [data-testid="stCaptionContainer"],
.st-key-ai-district-cycle-response [data-testid="stCaptionContainer"],
.st-key-ai-heatmap-response [data-testid="stCaptionContainer"] {
  color: #53D6D1 !important;
  font-weight: 700;
  letter-spacing: 0.055em;
}

/* ─── MAIN CONTAINER ─── */
.block-container {
  padding-top: 1.5rem !important;
  padding-bottom: 3rem !important;
  max-width: 1480px;
}

/* ─── SIDEBAR ─── */
[data-testid="stSidebar"] {
  background: var(--bg-base);
  border-right: 1px solid var(--border);
  background-image: linear-gradient(180deg, rgba(53,201,208,0.04) 0%, transparent 30%);
}
[data-testid="stSidebar"] * {
  font-family: 'Urbanist', sans-serif !important;
}

/* ─── TYPOGRAPHY ─── */
h1, h2, h3 {
  font-family: 'Urbanist', sans-serif !important;
  color: var(--text-primary) !important;
  letter-spacing: -0.02em;
}
h1 { font-weight: 800 !important; }
h2 { font-weight: 700 !important; }
h3 { font-weight: 600 !important; }

p, label, span, li {
  color: var(--text-secondary);
  font-family: 'Urbanist', sans-serif !important;
}

code, pre {
  font-family: 'Urbanist', sans-serif !important;
}

/* ─── METRIC TILES ─── */
[data-testid="stMetric"] {
  background: var(--bg-card);
  border: 1px solid var(--border);
  padding: 18px 20px !important;
  border-radius: var(--radius) !important;
  transition: var(--transition);
}
[data-testid="stMetric"]:hover {
  border-color: var(--border-active);
  background: var(--bg-card-hover);
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}
[data-testid="stMetricValue"] {
  color: var(--text-primary) !important;
  font-family: 'Urbanist', sans-serif !important;
  font-weight: 700;
  font-size: 1.6rem !important;
}
[data-testid="stMetricLabel"] {
  color: var(--text-muted) !important;
  font-size: 0.72rem !important;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* ─── GLASS CARD ─── */
.glass-card {
  background: linear-gradient(145deg, rgba(15,26,46,0.95), rgba(10,16,32,0.95));
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  transition: var(--transition);
  box-shadow: 0 2px 12px rgba(0,0,0,0.3);
}
.glass-card:hover {
  border-color: var(--border-active);
  box-shadow: 0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px var(--accent-glow);
  transform: translateY(-2px);
}

/* ─── AI CARD ─── */
.ai-card {
  background: linear-gradient(145deg, rgba(15,26,46,0.98), rgba(12,20,38,0.98));
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: var(--radius);
  padding: 22px 26px;
  margin-top: 10px;
  line-height: 1.75;
  font-size: 15px;
  color: var(--text-primary);
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
.ai-card strong {
  color: var(--accent);
  font-weight: 600;
}
.ai-card li {
  margin-bottom: 8px;
  color: var(--text-primary);
}
.ai-card ul {
  padding-left: 20px;
  margin: 8px 0;
}

/* ─── BADGE ─── */
.ep-badge {
  display: inline-block;
  background: rgba(53,201,208,0.1);
  border: 1px solid rgba(53,201,208,0.3);
  border-radius: 6px;
  padding: 3px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-family: 'Urbanist', sans-serif !important;
}

/* ─── SECTION HEADER ─── */
.ep-section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 28px 0 16px 0;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}
.ep-section-header .ep-icon {
  font-size: 24px;
  min-width: 32px;
}
.ep-section-header h2 {
  margin: 0;
  font-size: 1.35rem;
  font-weight: 700;
  color: var(--text-primary) !important;
}
.ep-section-header .ep-sub {
  font-size: 0.85rem;
  color: var(--text-muted);
  margin-left: auto;
}

/* ─── STAT PILL ─── */
.stat-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 600;
  font-family: 'Urbanist', sans-serif !important;
}

/* ─── HERO BANNER ─── */
.hero-banner {
  background: linear-gradient(135deg, rgba(15,26,46,0.9), rgba(6,11,20,0.9));
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 40px 44px;
  margin-bottom: 28px;
  position: relative;
  overflow: hidden;
}
.hero-banner::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0; bottom: 0;
  background: radial-gradient(ellipse 60% 80% at 80% 50%, rgba(53,201,208,0.08), transparent);
  pointer-events: none;
}

/* ─── INFO BANNER ─── */
.ep-banner {
  border-radius: var(--radius);
  padding: 16px 20px;
  margin: 12px 0;
  font-size: 14px;
  line-height: 1.6;
  border: 1px solid;
}
.ep-banner.info {
  background: rgba(53,201,208,0.06);
  border-color: rgba(53,201,208,0.2);
  color: var(--text-secondary);
}
.ep-banner.warning {
  background: rgba(233,163,75,0.06);
  border-color: rgba(233,163,75,0.2);
  color: var(--text-secondary);
}
.ep-banner.success {
  background: rgba(49,196,141,0.06);
  border-color: rgba(49,196,141,0.2);
  color: var(--text-secondary);
}

/* ─── BUTTONS ─── */
.stButton > button {
  background: var(--bg-card) !important;
  border: 1px solid var(--border) !important;
  border-radius: var(--radius-sm) !important;
  color: var(--text-primary) !important;
  font-family: 'Urbanist', sans-serif !important;
  font-weight: 500 !important;
  font-size: 14px !important;
  padding: 10px 20px !important;
  transition: var(--transition) !important;
}
.stButton > button:hover {
  border-color: var(--accent) !important;
  background: var(--bg-card-hover) !important;
  color: var(--accent) !important;
  box-shadow: 0 0 0 3px var(--accent-glow) !important;
}

/* ─── PRIMARY BUTTON ─── */
.ep-primary-btn {
  background: linear-gradient(135deg, rgba(53,201,208,0.15), rgba(108,142,230,0.1)) !important;
  border: 1px solid var(--accent) !important;
}

/* ─── DATAFRAME ─── */
.stDataFrame {
  border-radius: var(--radius);
  overflow: hidden;
}
[data-testid="stDataFrame"] {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-card);
  box-shadow: 0 10px 28px rgba(0,0,0,0.18);
  overflow: hidden;
}

/* ─── EXPANDER ─── */
[data-testid="stExpander"] {
  border: 1px solid var(--border) !important;
  border-radius: var(--radius) !important;
  background: var(--bg-card) !important;
}
[data-testid="stExpander"] > details > summary {
  font-family: 'Urbanist', sans-serif !important;
  font-weight: 600;
}

/* ─── SELECTBOX / INPUT ─── */
[data-baseweb="select"] > div {
  border-color: var(--border) !important;
  background: var(--bg-card) !important;
  border-radius: var(--radius-sm) !important;
}
[data-baseweb="select"]:hover > div {
  border-color: var(--border-active) !important;
}

/* ─── PLOTLY CHART CONTAINER ─── */
.stPlotlyChart {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg-card);
}

/* ─── CHAT MESSAGE ─── */
[data-testid="stChatMessage"] {
  border: 1px solid var(--border);
  border-radius: var(--radius) !important;
  background: var(--bg-card) !important;
}

/* ─── HORIZONTAL SCROLLBAR ─── */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}
::-webkit-scrollbar-track {
  background: var(--bg-base);
}
::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--border-active);
}

/* ─── DIVIDER ─── */
hr {
  border-color: var(--border) !important;
  margin: 2rem 0 !important;
}

/* ─── CAPTION ─── */
.stCaption {
  color: var(--text-muted) !important;
  font-size: 0.8rem !important;
}

/* ─── FOOTER ─── */
.ep-footer {
  text-align: center;
  padding: 24px 0 0 0;
  border-top: 1px solid var(--border);
  margin-top: 2rem;
}
.ep-footer span {
  font-size: 12px;
  color: var(--text-muted);
  font-family: 'Urbanist', sans-serif !important;
  letter-spacing: 0.03em;
}
</style>
"""


def inject_theme():
    """Call this at the top of every page after set_page_config."""
    st.markdown(_PREMIUM_CSS, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────
# 2. REUSABLE UI COMPONENTS
# ──────────────────────────────────────────────────────────────

def page_header(title: str, subtitle: str, icon: str = "🌍"):
    """Premium page header with gradient banner."""
    st.markdown(f"""
    <div class="hero-banner">
      <div style="position: relative; z-index: 1;">
        <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 8px;">
          <span style="font-size: 38px;">{icon}</span>
          <div>
            <h1 style="margin: 0; font-size: 2rem; font-weight: 800;
                       color: var(--text-primary); letter-spacing: -0.03em;">
              {title}
            </h1>
          </div>
        </div>
        <p style="margin: 6px 0 0 0; font-size: 1.05rem; color: var(--text-secondary);">
          {subtitle}
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)


def section_header(title: str, icon: str = "📊", subtitle: str = ""):
    """Section divider with icon and optional subtitle."""
    sub_html = f'<span class="ep-sub">{subtitle}</span>' if subtitle else ""
    st.markdown(f"""
    <div class="ep-section-header">
      <span class="ep-icon">{icon}</span>
      <h2>{title}</h2>
      {sub_html}
    </div>
    """, unsafe_allow_html=True)


def badge(text: str):
    """Small accent badge."""
    st.markdown(f'<span class="ep-badge">{text}</span>', unsafe_allow_html=True)


def info_banner(text: str, kind: str = "info"):
    """Colored info banner."""
    st.markdown(f'<div class="ep-banner {kind}">{text}</div>', unsafe_allow_html=True)


def stat_pill(label: str, value: str, color: str = "#35C9D0"):
    """Inline stat pill."""
    st.markdown(
        f'<span class="stat-pill" style="border-color:{color}40; color:{color};">'
        f'{label}: <strong style="color:var(--text-primary)">{value}</strong></span>',
        unsafe_allow_html=True,
    )


def md_to_html(text: str) -> str:
    """Convert markdown bold + bullet lists to HTML for styled card."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    lines = text.split("\n")
    html_lines = []
    in_list = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if stripped:
                html_lines.append(f"<p>{stripped}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def ai_card(text: str):
    """Render AI explanation in a styled card."""
    st.markdown(
        f'<div class="ai-card">{md_to_html(text)}</div>',
        unsafe_allow_html=True,
    )


def footer():
    """Standard footer."""
    st.markdown(
        '<div class="ep-footer">'
        '<span>EARTHPULSE-X · UG-ESI · Uncertainty-Guided Earth System Intelligence · '
        'NASA Space Apps 2026</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def glass_card(content: str):
    """Render content inside a glass card."""
    st.markdown(
        f'<div class="glass-card">{content}</div>',
        unsafe_allow_html=True,
    )
