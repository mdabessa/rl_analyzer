"""Consultas ao warehouse DuckDB (compartilhadas pelas páginas do app).

Lê o ``data/warehouse.duckdb`` (tabelas silver + views gold) criado por
``scripts/build_warehouse.py``.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import duckdb
import pandas as pd

# Garante o import de src.constants (RANKS) a partir de qualquer cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.constants import RANKS  # noqa: E402

WAREHOUSE = Path(__file__).resolve().parent.parent / "data" / "warehouse.duckdb"


@lru_cache(maxsize=1)
def _con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(WAREHOUSE), read_only=True)


def _df(sql: str, params: tuple = ()) -> pd.DataFrame:
    return _con().execute(sql, params).fetchdf()


def warehouse_exists() -> bool:
    return WAREHOUSE.exists()


def population_totals() -> dict:
    row = _df(
        """
        SELECT
          (SELECT count(*) FROM replays)             AS n_replays,
          (SELECT count(*) FROM players)             AS n_players,
          (SELECT count(*) FROM v_replays_by_bucket) AS n_buckets,
          (SELECT count(*) FROM v_top_players)       AS n_top_players
        """
    ).iloc[0]
    return row.to_dict()


def seasons() -> list:
    return _df("SELECT DISTINCT season FROM replays ORDER BY 1")["season"].tolist()


def playlists() -> list:
    return _df("SELECT DISTINCT playlist_id FROM replays ORDER BY 1")["playlist_id"].tolist()


def replays_by_bucket(season=None, playlist=None) -> pd.DataFrame:
    sql = "SELECT * FROM v_replays_by_bucket"
    conds, params = [], []
    if season:
        conds.append("season = ?")
        params.append(season)
    if playlist:
        conds.append("playlist_id = ?")
        params.append(playlist)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY season, playlist_id, tier"
    return _df(sql, tuple(params))


def players_by_bucket(season=None, playlist=None) -> pd.DataFrame:
    sql = "SELECT * FROM v_players_by_bucket"
    conds, params = [], []
    if season:
        conds.append("season = ?")
        params.append(season)
    if playlist:
        conds.append("playlist_id = ?")
        params.append(playlist)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY season, playlist_id, tier, team"
    return _df(sql, tuple(params))


def top_players(limit: int = 20, playlist=None) -> pd.DataFrame:
    sql = (
        "SELECT name, platform, player_uid, playlist_id, n_replays, "
        "total_goals, total_score, avg_score FROM v_top_players"
    )
    conds, params = [], []
    if playlist:
        conds.append("playlist_id = ?")
        params.append(playlist)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY n_replays DESC LIMIT ?"
    params.append(limit)
    return _df(sql, tuple(params))


# --- nomes amigáveis ------------------------------------------------------

QUEUE_NAMES = {
    "ranked-doubles": "Duplas",
    "ranked-duels": "1v1",
    "ranked-standard": "3v3",
}


def tier_name(tier) -> str:
    """Nome do rank a partir do tier (1-based, da API)."""
    try:
        return RANKS[int(tier) - 1]
    except (IndexError, ValueError):
        return f"Tier {tier}"


def queue_name(playlist) -> str:
    return QUEUE_NAMES.get(playlist, playlist)


# --- agregações -----------------------------------------------------------


def _where(season, playlist, params: list, alias: str = "") -> str:
    """Monta WHERE com filtros; aceita valor único ou lista (IN)."""
    def col(name: str) -> str:
        return f"{alias}.{name}" if alias else name

    conds = []
    if season:
        if isinstance(season, (list, tuple)):
            marks = ", ".join("?" for _ in season)
            conds.append(f"{col('season')} IN ({marks})")
            params.extend(list(season))
        else:
            conds.append(f"{col('season')} = ?")
            params.append(season)
    if playlist:
        if isinstance(playlist, (list, tuple)):
            marks = ", ".join("?" for _ in playlist)
            conds.append(f"{col('playlist_id')} IN ({marks})")
            params.extend(list(playlist))
        else:
            conds.append(f"{col('playlist_id')} = ?")
            params.append(playlist)
    return (" WHERE " + " AND ".join(conds)) if conds else ""


def totals(season=None, playlist=None) -> dict:
    """Replays e players respeitando os filtros (aceita lista)."""
    params: list = []
    where = _where(season, playlist, params)
    n_replays = _df(f"SELECT count(*) FROM replays {where}", tuple(params)).iloc[0, 0]
    n_players = _df(f"SELECT count(*) FROM players {where}", tuple(params)).iloc[0, 0]
    return {"n_replays": int(n_replays), "n_players": int(n_players)}


def population_by(dimension: str, season=None, playlist=None) -> pd.DataFrame:
    """Agrega população (replays + players) por 'season' | 'playlist_id' | 'tier'."""
    if dimension not in {"season", "playlist_id", "tier"}:
        raise ValueError(f"dimensão inválida: {dimension}")

    params_r: list = []
    r = _df(
        f"SELECT r.{dimension} AS k, count(*) AS n_replays "
        f"FROM replays r {_where(season, playlist, params_r, 'r')} GROUP BY 1",
        tuple(params_r),
    )
    params_p: list = []
    p = _df(
        f"SELECT p.{dimension} AS k, count(*) AS n_players "
        f"FROM players p {_where(season, playlist, params_p, 'p')} GROUP BY 1",
        tuple(params_p),
    )
    df = r.merge(p, on="k", how="outer").fillna(0)
    df["n_replays"] = df["n_replays"].astype(int)
    df["n_players"] = df["n_players"].astype(int)
    return df.sort_values("k").reset_index(drop=True)


def population_cross(dim1: str, dim2: str, season=None, playlist=None) -> pd.DataFrame:
    """Replays por (dim1, dim2) — ex.: season × tier para heatmap."""
    params: list = []
    where = _where(season, playlist, params)
    sql = (
        f"SELECT {dim1} AS d1, {dim2} AS d2, count(*) AS n_replays "
        f"FROM replays {where} GROUP BY 1, 2"
    )
    return _df(sql, tuple(params))
