#!/usr/bin/env python3
"""Atribui rótulos de dados (train/validation/test/demo) aos replays.

Por que um mapeamento e não uma coluna dentro do Parquet?
- O Parquet é imutável: "preencher só as linhas NULL sem tocar nas já rotuladas"
  não é possível em arquivos grandes (qualquer escrita reescreve a partição).
- Um mapeamento pequeno (1 linha por replay_id) é a fonte de verdade do split:
  roda de novo e só os replays NOVOS são rotulados; `--force` re-rotula todos.
- No treino, basta um LEFT JOIN por replay_id (players e replays têm replay_id).

Regras (anti-vazamento):
- Divisão por **replay_id**: os 2/4/6 jogadores da mesma partida ficam juntos.
- **Determinística**: hash estável (md5) de `playlist:replay_id:seed` -> [0,1).
  Replays novos recebem o MESMO rótulo que receberiam se existissem desde o
  início; rodar de novo NÃO re-atribui os já rotulados.
- **Por playlist** (1 modelo por playlist): a semente inclui a playlist, então a
  proporção vale dentro de cada playlist (e aproximadamente por tier).
- Buckets: 'train' | 'validation' (comparar modelos) | 'test' (avaliação final,
  usar uma vez) | 'demo' (reserva disjunta p/ demos/dashboards — nunca treinar).
- Linhas sem rótulo = "ainda não classificadas" (NULL no LEFT JOIN).

Atenção: divisão por tempo (inflação de rank ao longo das temporadas) deve ser
avaliada como experimento à parte (walk-forward), não como coluna fixa — este
script é estável/atemporal por construção.

Exemplos:
    python3 scripts/prepare_split.py --data-dir data
    python3 scripts/prepare_split.py --data-dir data --force          # re-rotula tudo
    python3 scripts/prepare_split.py --data-dir data --demo 0.03 --validation 0.10 --test 0.20

Uso no treino (players por replay):
    SELECT p.*, s.data_split
    FROM read_parquet('data/parquet/players/**/*.parquet') p
    LEFT JOIN read_parquet('data/splits.parquet') s USING (replay_id)
    WHERE s.data_split = 'train'
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import duckdb

DEFAULT_DEMO = 0.02  # reserva disjunta p/ demos/dashboards (por playlist)
DEFAULT_VALIDATION = 0.10
DEFAULT_TEST = 0.20  # avaliação final (usar uma vez)
# train = resto (1 - demo - validation - test)

SPLITS_FILE = "splits.parquet"
STATE_FILE = "splits_state.json"


def _stable_u(playlist_id: str, replay_id: str, seed: str) -> float:
    """Valor pseudo-aleatório estável em [0,1) p/ (playlist, replay)."""
    h = hashlib.md5(f"{playlist_id}:{replay_id}:{seed}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) / 2**32


def _bucket(u: float, demo: float, validation: float, test: float) -> str:
    if u < demo:
        return "demo"
    if u < demo + validation:
        return "validation"
    if u < demo + validation + test:
        return "test"
    return "train"


def _load_existing(splits_path: Path) -> dict[str, str]:
    """replay_id -> data_split (se o arquivo de splits já existir)."""
    if not splits_path.is_file():
        return {}
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT replay_id, data_split FROM read_parquet('{splits_path}')"
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        con.close()


def _population(data_dir: Path) -> list[tuple[str, str, int]]:
    """(replay_id, playlist_id, tier) distintos vistos no Parquet de replays."""
    replays = data_dir / "parquet" / "replays"
    if not replays.is_dir() or not any(replays.rglob("*.parquet")):
        raise FileNotFoundError(
            f"Sem Parquet de replays em {replays} — rode build_silver primeiro."
        )
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT DISTINCT replay_id, playlist_id, tier "
            f"FROM read_parquet('{replays}/**/*.parquet')"
        ).fetchall()
        return [(r[0], r[1], int(r[2])) for r in rows if r[0] is not None]
    finally:
        con.close()


def _write_splits(splits_path: Path, rows: list[tuple]) -> None:
    splits_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = splits_path.with_name(splits_path.name + ".tmp")
    con = duckdb.connect()
    try:
        con.execute(
            "CREATE OR REPLACE TEMP TABLE _s "
            "(replay_id VARCHAR, playlist_id VARCHAR, tier BIGINT, data_split VARCHAR)"
        )
        con.executemany("INSERT INTO _s VALUES (?, ?, ?, ?)", rows)
        con.execute(
            f"COPY (SELECT * FROM _s ORDER BY playlist_id, replay_id) "
            f"TO '{tmp}' (FORMAT PARQUET)"
        )
    finally:
        con.close()
    tmp.replace(splits_path)  # escrita atômica


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Atribui train/validation/test/demo por replay_id (mapeamento "
            "incremental; só replays novos são rotulados a menos que --force)."
        )
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Pasta base do data lake (default: %(default)s)",
    )
    parser.add_argument(
        "--demo",
        type=float,
        default=DEFAULT_DEMO,
        help="Fração reservada p/ demo (default: %(default)s)",
    )
    parser.add_argument(
        "--validation",
        type=float,
        default=DEFAULT_VALIDATION,
        help="Fração de validação (default: %(default)s)",
    )
    parser.add_argument(
        "--test",
        type=float,
        default=DEFAULT_TEST,
        help="Fração de teste final (default: %(default)s)",
    )
    parser.add_argument(
        "--seed",
        type=str,
        default="v1",
        help="Semente/método (mudar = re-rotular com --force)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-rotula TODA a população (ignora rótulos existentes)",
    )
    args = parser.parse_args(argv)

    train = 1.0 - args.demo - args.validation - args.test
    if train <= 0:
        parser.error("demo + validation + test precisa ser < 1 (sobra p/ train)")

    data_dir = Path(args.data_dir)
    splits_path = data_dir / SPLITS_FILE
    state_path = data_dir / STATE_FILE

    population = _population(data_dir)
    existing = {} if args.force else _load_existing(splits_path)

    # incremental: mantém os rótulos existentes e só atribui os replays novos.
    # --force: re-atribui a população inteira com os parâmetros atuais.
    rows: list[tuple] = []
    todo_count = 0
    for replay_id, playlist_id, tier in population:
        if not args.force and replay_id in existing:
            rows.append((replay_id, playlist_id, tier, existing[replay_id]))
            continue
        todo_count += 1
        u = _stable_u(playlist_id, replay_id, args.seed)
        split = _bucket(u, args.demo, args.validation, args.test)
        rows.append((replay_id, playlist_id, tier, split))

    # audita antes de gravar
    counts: dict[str, dict[str, int]] = {}
    for _rid, pl, _tier, split in rows:
        counts.setdefault(pl, {}).setdefault(split, 0)
        counts[pl][split] += 1

    print(f"População: {len(population):,} replays | novos p/ rotular: "
          f"{todo_count:,} | {splits_path}")
    for pl in sorted(counts):
        c = counts[pl]
        total = sum(c.values())
        parts = "  ".join(
            f"{k}={c.get(k, 0):,} ({c.get(k, 0) / total:.1%})"
            for k in ("train", "validation", "test", "demo")
        )
        print(f"  {pl:<18} {total:>7,} | {parts}")

    _write_splits(splits_path, rows)
    state = {
        "method": "replay-hash",
        "seed": args.seed,
        "ratios": {"demo": args.demo, "validation": args.validation, "test": args.test},
        "n_replays": len(population),
        "n_tagged": len(rows),
        "splits_file": str(splits_path),
    }
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
