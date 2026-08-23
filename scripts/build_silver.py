#!/usr/bin/env python3
"""Gera a camada Silver (Parquet) a partir do bronze (JSONs crus).

Exemplos:
    python3 scripts/build_silver.py --data-dir ./data
    python3 scripts/build_silver.py --data-dir /mnt/nextcloud/rl_data \
        --output-dir /mnt/nextcloud/rl_data/parquet
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
    args = parser.parse_args(argv)

    data_dir = Path(args.data_dir)
    out_dir = Path(args.output_dir) if args.output_dir else data_dir / "parquet"

    build_silver(data_dir, out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
