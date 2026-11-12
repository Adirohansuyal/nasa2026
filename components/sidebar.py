"""
Premium Sidebar for EARTHPULSE-X
================================
Import and call render_sidebar() on every page.
"""

import streamlit as st
from config import (
    APP_NAME,
    APP_VERSION,
    STUDY_REGION,
    ANALYSIS_START,
    ANALYSIS_END,
)
from core.data_loader import get_data_status


def render_sidebar():
    """Premium sidebar with mission info, data status, and navigation."""
    with st.sidebar:
        st.markdown("""
        <style>
        .ep-nav-title {
            font-family: 'Urbanist', sans-serif;
            font-size: 1.35rem;
            font-weight: 800;
            color: #F1F5FC;
            letter-spacing: -0.02em;
            margin-bottom: 2px;
        }
        .ep-nav-sub {
            font-size: 0.72rem;
            color: #6B7B91;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            font-weight: 600;
        }
        .ep-nav-card {
            background: #0F1A2E;
            border: 1px solid #1E2D4A;
            border-radius: 10px;
            padding: 14px 16px;
            margin: 8px 0;
        }
        .ep-nav-item {
            font-size: 0.8rem;
            color: #AAB8CC;
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 2px 0;
        }
        .ep-nav-dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            display: inline-block;
        }
        </style>
        """, unsafe_allow_html=True)

        st.markdown("""
        <div style="display:flex; align-items:center; gap:10px; margin-bottom:20px;">
            <span style="font-size:28px;">🌍</span>
            <div>
                <div class="ep-nav-title">EARTHPULSE-X</div>
                <div class="ep-nav-sub">Earth System Trend Detective</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("### 🎯 Mission Parameters")
        st.markdown(f"""
        <div class="ep-nav-card">
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#35C9D0;"></span>
                <strong style="color:#F1F5FC;">Region:</strong> {STUDY_REGION}
            </div>
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#6C8EE6;"></span>
                <strong style="color:#F1F5FC;">Period:</strong> {ANALYSIS_START[:7]} → {ANALYSIS_END[:7]}
            </div>
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#E9A34B;"></span>
                <strong style="color:#F1F5FC;">Satellites:</strong> MODIS · SMAP · GPM
            </div>
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#31C48D;"></span>
                <strong style="color:#F1F5FC;">Variables:</strong> LST · NDVI · SM · Rainfall
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Data status
        st.markdown("### 📊 Data Engine")
        try:
            status = get_data_status()
            st.markdown(f"""
            <div class="ep-nav-card">
                <div class="ep-nav-item">
                    <span class="ep-nav-dot" style="background:#31C48D;"></span>
                    Monthly datasets: <strong style="color:#F1F5FC;">{status['monthly_files']}</strong>
                </div>
                <div class="ep-nav-item">
                    <span class="ep-nav-dot" style="background:{'#31C48D' if status['regional_timeseries'] else '#EF6461'};"></span>
                    Regional time-series: {'✅' if status['regional_timeseries'] else '❌'}
                </div>
                <div class="ep-nav-item">
                    <span class="ep-nav-dot" style="background:{'#31C48D' if status['interaction_results'] else '#EF6461'};"></span>
                    Interaction analysis: {'✅' if status['interaction_results'] else '❌'}
                </div>
                <div class="ep-nav-item">
                    <span class="ep-nav-dot" style="background:{'#31C48D' if status['district_results'] else '#EF6461'};"></span>
                    District intelligence: {'✅' if status['district_results'] else '❌'}
                </div>
                <div class="ep-nav-item">
                    <span class="ep-nav-dot" style="background:{'#31C48D' if status['district_boundaries'] else '#E9A34B'};"></span>
                    District boundaries: {'✅' if status['district_boundaries'] else '⚠️'}
                </div>
            </div>
            """, unsafe_allow_html=True)
        except Exception:
            pass

        st.markdown("""
        <div class="ep-nav-card">
            <div style="font-size:0.72rem; font-weight:600; color:#6B7B91;
                        letter-spacing:0.06em; text-transform:uppercase;
                        margin-bottom:8px;">Methodology</div>
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#35C9D0;"></span>
                Modified Mann-Kendall
            </div>
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#35C9D0;"></span>
                Sen's Slope
            </div>
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#35C9D0;"></span>
                FDR Correction (BH)
            </div>
            <div class="ep-nav-item">
                <span class="ep-nav-dot" style="background:#35C9D0;"></span>
                Evidence-Grounded AI
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.divider()
        st.caption(f"Version {APP_VERSION} · NASA Space Apps 2026")
