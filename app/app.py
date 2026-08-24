"""Rocket League Analyzer — dashboard (Streamlit).

Roda com:
    streamlit run app/app.py

Lê o warehouse DuckDB (``data/warehouse.duckdb``). Páginas laterais:
- População: por temporada, fila e rank.
- Validação: auditoria de qualidade (manifests × arquivos, stubs, buracos).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

import app.queries as q
import app.theme as theme

theme.page_config()
theme.apply()
theme.header("Replays de Rocket League (Ballchasing) · DuckDB warehouse")

if not q.warehouse_exists():
    st.error("Warehouse não encontrado: data/warehouse.duckdb")
    st.info("Rode primeiro: `python3 scripts/build_warehouse.py --data-dir data`")
    st.stop()

totals = q.population_totals()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Replays", f"{totals['n_replays']:,}")
c2.metric("Observações de players", f"{totals['n_players']:,}")
c3.metric("Buckets (season × fila × tier)", f"{totals['n_buckets']:,}")
c4.metric("Jogadores (top)", f"{totals['n_top_players']:,}")

st.divider()

by_season = q.population_by("season")
by_queue = q.population_by("playlist_id")
by_queue["label"] = by_queue["k"].map(q.queue_name)

left, right = st.columns(2)
with left:
    st.subheader("Replays por temporada")
    fig = px.bar(
        by_season, x="k", y="n_replays",
        color_discrete_sequence=["#4f46e5"],
        labels={"k": "Temporada", "n_replays": "Replays"},
    )
    fig.update_layout(showlegend=False, height=320, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch")

with right:
    st.subheader("Replays por fila")
    fig = px.bar(
        by_queue, x="label", y="n_replays", color="label",
        labels={"label": "Fila", "n_replays": "Replays"},
    )
    fig.update_layout(height=320, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch")

st.divider()
st.subheader("Top jogadores por nº de replays")
st.dataframe(q.top_players(limit=20), width="stretch", height=320, hide_index=True)

st.info("Use o menu lateral para **População** (por temporada/fila/rank) e **Validação** (qualidade).")
