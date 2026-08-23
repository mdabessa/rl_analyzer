"""Camada Silver (medallion): bronze (JSONs crus) -> Parquet colunar particionado.

Lê os JSONs do bronze com DuckDB e escreve duas tabelas Parquet (silver),
particionadas por ``season/playlist_id/tier`` (estilo Hive):

- ``replays``: 1 linha por replay (campos do topo + agregados dos times).
- ``players``: 1 linha por jogador por replay (base para o ML/população).

Depende apenas de DuckDB (sem pandas/pyarrow).
"""

from __future__ import annotations

from pathlib import Path

import duckdb

# Normaliza a temporada: a API pode devolver inteiro (12) ou string ("f12").
SEASON_SQL = (
    "CASE WHEN CAST(r.season AS VARCHAR) LIKE 'f%' "
    "THEN CAST(r.season AS VARCHAR) "
    "ELSE 'f' || CAST(r.season AS VARCHAR) END"
)


def _replays_sql(glob: str) -> str:
    return f"""
    SELECT
        CAST(r.id AS VARCHAR)                        AS replay_id,
        {SEASON_SQL}                                 AS season,
        r.playlist_id,
        r.min_rank.tier                              AS tier,
        r.min_rank.division                          AS division,
        r.date,
        r.duration,
        r.map_code,
        r.map_name,
        r.team_size,
        r.overtime,
        r.status,
        r.blue.stats.core.goals                      AS blue_goals,
        r.orange.stats.core.goals                    AS orange_goals,
        r.blue.stats.core.score                      AS blue_score,
        r.orange.stats.core.score                    AS orange_score,
        r.blue.stats.core.shots                      AS blue_shots,
        r.orange.stats.core.shots                    AS orange_shots,
        r.blue.stats.core.saves                      AS blue_saves,
        r.orange.stats.core.saves                    AS orange_saves,
        (r.blue.stats.core.goals > r.orange.stats.core.goals) AS blue_won
    FROM read_json_auto('{glob}') AS r
    """


def _players_sql(glob: str) -> str:
    return f"""
    WITH teams AS (
        SELECT
            CAST(r.id AS VARCHAR)  AS id,
            {SEASON_SQL}           AS season,
            r.playlist_id,
            r.min_rank.tier        AS tier,
            r.date,
            r.duration,
            (r.blue.stats.core.goals > r.orange.stats.core.goals) AS blue_winner,
            t.team_name,
            CASE t.team_name WHEN 'blue' THEN r.blue.players ELSE r.orange.players END AS players
        FROM read_json_auto('{glob}') AS r
        CROSS JOIN (VALUES ('blue'), ('orange')) AS t(team_name)
    )
    SELECT
        te.id                                        AS replay_id,
        te.season,
        te.playlist_id,
        te.tier,
        te.date,
        te.duration,
        te.team_name                                 AS team,
        p.id.platform                                AS platform,
        p.id.id                                      AS player_uid,
        p.name,
        p.mvp,
        p.start_time,
        p.end_time,
        p.stats,
        p.stats.core.goals                           AS goals,
        p.stats.core.assists                         AS assists,
        p.stats.core.saves                           AS saves,
        p.stats.core.shots                           AS shots,
        p.stats.core.score                           AS score,
        p.stats.core.shooting_percentage             AS shooting_pct,
        (te.team_name = 'blue') = te.blue_winner     AS winner,
        te.id || '.' || p.id.platform || '.' || p.id.id AS player_key
    FROM teams te, LATERAL (SELECT UNNEST(te.players) AS p) u
    """


def build_silver(data_dir: str | Path, out_dir: str | Path) -> None:
    """Lê o bronze em ``data_dir`` e escreve o Parquet silver em ``out_dir``."""
    data_dir = Path(data_dir)
    out_dir = Path(out_dir)
    glob = str(data_dir / "replays" / "**" / "*.json")
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    try:
        print(f"Lendo bronze: {glob}")
        for name, sql in (
            ("replays", _replays_sql(glob)),
            ("players", _players_sql(glob)),
        ):
            dest = out_dir / name
            dest.mkdir(parents=True, exist_ok=True)
            con.execute(
                f"""
                COPY ({sql})
                TO '{dest}'
                (FORMAT PARQUET, PARTITION_BY (season, playlist_id, tier),
                 OVERWRITE_OR_IGNORE)
                """
            )
            n = con.execute(
                f"SELECT count(*) FROM read_parquet('{dest}/**/*.parquet')"
            ).fetchone()[0]
            print(f"  {name}: {n:,} linhas -> {dest}")
    finally:
        con.close()
