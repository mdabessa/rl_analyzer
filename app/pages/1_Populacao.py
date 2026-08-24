"""População por temporada, fila e rank."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import plotly.express as px
import streamlit as st

import app.queries as q
import app.theme as theme

theme.page_config(title="Rocket League Analyzer — População")
theme.apply()
theme.header("População disponível · por temporada, fila e rank")

if not q.warehouse_exists():
    st.error("Warehouse não encontrado: data/warehouse.duckdb")
    st.info("Rode: `python3 scripts/build_warehouse.py --data-dir data`")
    st.stop()

seasons = q.seasons()
playlists = q.playlists()

with st.sidebar:
    st.caption("Filtros")
    sel_season = st.multiselect("Temporadas", seasons, default=seasons)
    sel_playlist = st.multiselect("Filas", playlists, default=playlists)

sel_s = sel_season or None
sel_p = sel_playlist or None

t = q.totals(season=sel_s, playlist=sel_p)
c1, c2 = st.columns(2)
c1.metric("Replays (filtro)", f"{t['n_replays']:,}")
c2.metric("Observações de players (filtro)", f"{t['n_players']:,}")

st.divider()

tab_season, tab_queue, tab_rank, tab_heat = st.tabs(
    ["📅 Por temporada", "🎯 Por fila", "🏅 Por rank", "🗺️ Temporada × rank"]
)

with tab_season:
    df = q.population_by("season", season=sel_s, playlist=sel_p)
    fig = px.bar(
        df, x="k", y="n_replays",
        color_discrete_sequence=["#4f46e5"],
        labels={"k": "Temporada", "n_replays": "Replays"},
    )
    fig.update_layout(showlegend=False, height=340, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(
        df[["k", "n_replays", "n_players"]].rename(
            columns={"k": "Temporada", "n_replays": "Replays", "n_players": "Players"}
        ),
        width="stretch", hide_index=True,
    )

with tab_queue:
    df = q.population_by("playlist_id", season=sel_s, playlist=sel_p)
    df["label"] = df["k"].map(q.queue_name)
    fig = px.bar(
        df, x="label", y="n_replays", color="label",
        labels={"label": "Fila", "n_replays": "Replays"},
    )
    fig.update_layout(height=340, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch")
    st.dataframe(
        df[["k", "label", "n_replays", "n_players"]].rename(
            columns={"k": "Playlist", "label": "Fila", "n_replays": "Replays", "n_players": "Players"}
        ),
        width="stretch", hide_index=True,
    )

with tab_rank:
    df = q.population_by("tier", season=sel_s, playlist=sel_p)
    df["rank"] = df["k"].apply(q.tier_name)
    fig = px.bar(
        df, x="rank", y="n_replays",
        color_discrete_sequence=["#16a34a"],
        labels={"rank": "Rank", "n_replays": "Replays"},
    )
    fig.update_layout(
        showlegend=False, height=400, margin=dict(l=0, r=0, t=10, b=0),
        xaxis_categoryorder="array", xaxis_categoryarray=df["rank"].tolist(),
    )
    fig.update_xaxes(tickangle=-45)
    st.plotly_chart(fig, width="stretch")
    st.dataframe(
        df[["k", "rank", "n_replays", "n_players"]].rename(
            columns={"k": "Tier", "rank": "Rank", "n_replays": "Replays", "n_players": "Players"}
        ),
        width="stretch", hide_index=True,
    )

with tab_heat:
    cross = q.population_cross("season", "tier", season=sel_s, playlist=sel_p)
    cross["rank"] = cross["d2"].apply(q.tier_name)
    pivot = cross.pivot_table(index="rank", columns="d1", values="n_replays", aggfunc="sum").fillna(0)
    fig = px.imshow(
        pivot, text_auto=".0f", color_continuous_scale="Blues",
        labels=dict(x="Temporada", y="Rank", color="Replays"),
    )
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(fig, width="stretch")
    st.caption("Replays por temporada × rank (tier).")
