"""Tema/estilo compartilhado do dashboard (CSS + helpers)."""

from __future__ import annotations

import streamlit as st

PAGE_TITLE = "Rocket League Analyzer"
PAGE_ICON = "🎮"

_CSS = """
<style>
/* fundo geral */
.stApp { background-color: #f4f6fb; }
.block-container { padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1200px; }

/* cartões de métrica */
div[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e6e9f2;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 1px 3px rgba(16, 24, 40, 0.06);
}
div[data-testid="stMetricLabel"] p { color: #667085; font-size: 0.82rem; font-weight: 500; }
div[data-testid="stMetricValue"] { color: #101828; font-size: 1.7rem; font-weight: 700; }

/* títulos */
h1, h2, h3 { color: #101828; }
h1 { border-bottom: 3px solid #4f46e5; padding-bottom: 0.35rem; }
h3 { margin-top: 1.2rem; }

/* tabelas com cantos arredondados */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* sidebar clara */
section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #e6e9f2; }

/* botões */
.stButton > button {
    border-radius: 8px;
    border: 1px solid #d0d5dd;
    background: #ffffff;
    font-weight: 500;
}
.stButton > button:hover { border-color: #4f46e5; color: #4f46e5; }

/* subtítulo do cabeçalho */
.dashboard-caption { color: #667085; margin-top: -0.6rem; font-size: 0.95rem; }
</style>
"""


def apply() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def page_config(title: str | None = None, icon: str | None = None) -> None:
    st.set_page_config(
        page_title=title or PAGE_TITLE,
        page_icon=icon or PAGE_ICON,
        layout="wide",
        initial_sidebar_state="expanded",
    )


def header(subtitle: str | None = None) -> None:
    st.title(PAGE_TITLE)
    if subtitle:
        st.markdown(f'<p class="dashboard-caption">{subtitle}</p>', unsafe_allow_html=True)
