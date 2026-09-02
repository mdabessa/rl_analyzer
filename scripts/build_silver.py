#!/usr/bin/env python3
"""Gera a camada Silver (Parquet) a partir do bronze (JSONs crus).

O schema é descoberto dinamicamente de uma amostra do bronze (veja src/silver.py).

Exemplos:
    python3 scripts/build_silver.py --data-dir ./data
    python3 scripts/build_silver.py --data-dir /mnt/nextcloud/rl_data \
        --output-dir /mnt/nextcloud/rl_data/parquet
    python3 scripts/build_silver.py --data-dir ./data --sample-size 500 \
        --min-presence 0.05
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Garante que o pacote `src` seja importável a partir de qualquer cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.silver import build_silver  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gera a camada Silver (Parquet particionado) a partir do bronze (JSONs crus)."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Pasta base do bronze (default: %(default)s)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Onde gravar o Parquet (default: <data-dir>/parquet)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Replays sorteados para descobrir o schema (default: 1000)",
    )
    parser.add_argument(
        "--min-presence",
        type=float,
        default=None,
        help="Fração mínima p/ uma folha virar coluna (default: 0.01 = 1%%)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semente p/ amostra reproduzível (default: fixa/estável)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Força rebuild total, ignorando o estado incremental",
    )
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir) if args.output_dir else data_dir / "parquet"

    kwargs = {"force": args.force}
    if args.sample_size is not None:
        kwargs["sample_size"] = args.sample_size
    if args.min_presence is not None:
        kwargs["min_presence"] = args.min_presence
    if args.seed is not None:
        kwargs["seed"] = args.seed

    build_silver(data_dir, out_dir, **kwargs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
