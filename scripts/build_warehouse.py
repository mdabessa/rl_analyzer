#!/usr/bin/env python3
"""Cria o warehouse DuckDB (camada de consulta p/ Superset) a partir do silver.

Materializa o Parquet silver em tabelas DuckDB e cria views "gold" (agregações).
O arquivo ``warehouse.duckdb`` é autocontido — pode ser lido pelo Superset (ou
qualquer cliente) sem depender dos caminhos do Parquet.

Exemplos:
    python3 scripts/build_warehouse.py --data-dir ./data
    python3 scripts/build_warehouse.py --data-dir ./data --db data/warehouse.duckdb
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def build_warehouse(data_dir: str | Path, db_path: str | Path) -> Path:
    data_dir = Path(data_dir)
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    parquet_replays = str(data_dir / "parquet" / "replays" / "**" / "*.parquet")
    parquet_players = str(data_dir / "parquet" / "players" / "**" / "*.parquet")

    con = duckdb.connect(str(db_path))
    try:
        # --- silver (materializado em tabelas) ---
        con.execute(
            "CREATE OR REPLACE TABLE replays AS SELECT * FROM read_parquet(?)",
            [parquet_replays],
        )
        con.execute(
            "CREATE OR REPLACE TABLE players AS SELECT * FROM read_parquet(?)",
            [parquet_players],
        )

        # --- gold (views agregadas p/ dashboards) ---
        con.execute(
            """
            CREATE OR REPLACE VIEW v_replays_by_bucket AS
            SELECT season, playlist_id, tier,
                   count(*)                                  AS n_replays,
                   count(DISTINCT map_code)                  AS n_maps,
                   sum(CASE WHEN blue_won THEN 1 ELSE 0 END) AS n_blue_wins,
                   round(avg(duration), 0)                   AS avg_duration_s
            FROM replays
            GROUP BY season, playlist_id, tier
            """
        )
        con.execute(
            """
            CREATE OR REPLACE VIEW v_players_by_bucket AS
            SELECT season, playlist_id, tier, team,
                   count(*)                    AS n_players,
                   count(DISTINCT player_uid)  AS n_unique_players,
                   round(avg(goals), 2)        AS avg_goals,
                   round(avg(score), 0)        AS avg_score,
                   round(avg(shooting_pct), 1) AS avg_shooting_pct
            FROM players
            GROUP BY season, playlist_id, tier, team
            """
        )
        con.execute(
            """
            CREATE OR REPLACE VIEW v_top_players AS
            SELECT name, platform, player_uid, playlist_id,
                   count(*)                AS n_replays,
                   sum(goals)              AS total_goals,
                   sum(score)              AS total_score,
                   round(avg(score), 0)    AS avg_score
            FROM players
            WHERE name IS NOT NULL
            GROUP BY name, platform, player_uid, playlist_id
            """
        )

        # --- resumo ---
        print(f"Warehouse: {db_path}")
        for label, sql in (
            ("replays (silver)", "SELECT count(*) FROM replays"),
            ("players (silver)", "SELECT count(*) FROM players"),
            ("v_replays_by_bucket", "SELECT count(*) FROM v_replays_by_bucket"),
            ("v_players_by_bucket", "SELECT count(*) FROM v_players_by_bucket"),
            ("v_top_players", "SELECT count(*) FROM v_top_players"),
        ):
            n = con.execute(sql).fetchone()[0]
            print(f"  {label}: {n:,}")
    finally:
        con.close()
    return db_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cria o warehouse DuckDB (tabelas silver + views gold) para o Superset."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Pasta base (default: %(default)s)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Arquivo .duckdb de saída (default: <data-dir>/warehouse.duckdb)",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    db_path = Path(args.db) if args.db else data_dir / "warehouse.duckdb"
    build_warehouse(data_dir, db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
