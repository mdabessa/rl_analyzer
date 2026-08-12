#!/usr/bin/env python3
"""CLI do downloader de replays (Ballchasing -> data lake em pastas).

A pasta base (--data-dir) recebe replays/, manifests/ e state.json — ideal para
apontar para uma pasta sincronizada no Nextcloud (usada tanto local quanto VPS).

Exemplos:
    # rodar com a config padrão, usando o token da env BALLCHASING_TOKEN (ou .env)
    python3 scripts/download.py --data-dir /mnt/nextcloud/rl_data

    # uma única passada (1 página por bucket) para testar
    python3 scripts/download.py --data-dir ./data --once

    # token explícito e arquivo de log
    python3 scripts/download.py --data-dir ./data --token abc123 --log-file logs/download.log

    # sem loop infinito (encerra quando todos os buckets esgotarem)
    python3 scripts/download.py --data-dir ./data --rescan-interval 0
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import ballchasing_api as api  # noqa: E402
from src.downloader import Downloader  # noqa: E402


def _load_dotenv(path: str | Path) -> None:
    """Carrega um .env simples (KEY=value) para os.environ, sem dependência extra."""
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Baixa replays da Ballchasing para um data lake em pastas "
            "(particionado, com manifests e state para retomada)."
        )
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Pasta base (ex.: Nextcloud) onde ficam replays/, manifests/ e state.json",
    )
    parser.add_argument(
        "--config",
        default="config/download.yaml",
        help="Arquivo YAML de configuração (default: %(default)s)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Token da Ballchasing (sobrescreve env/.env)",
    )
    parser.add_argument(
        "--token-env",
        default="BALLCHASING_TOKEN",
        help="Nome da variável de ambiente com o token (default: %(default)s)",
    )
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Arquivo .env opcional (default: %(default)s)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Executa apenas uma passada (1 página por bucket) e sai",
    )
    parser.add_argument(
        "--rescan-interval",
        type=float,
        default=None,
        help="Sobrescreve rescan_interval do config em segundos (0 desliga o loop infinito)",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Caminho opcional de arquivo de log",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Log em nível DEBUG",
    )
    return parser


def setup_logging(args: argparse.Namespace) -> None:
    level = logging.DEBUG if args.verbose else logging.INFO
    handlers = [logging.StreamHandler()]
    if args.log_file:
        log_path = Path(args.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )


def load_config(args: argparse.Namespace, parser: argparse.ArgumentParser) -> dict:
    path = Path(args.config)
    if not path.exists():
        parser.error(f"Config não encontrado: {path}")
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if args.rescan_interval is not None:
        config["rescan_interval"] = args.rescan_interval
    return config


def resolve_token(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    if args.token:
        return args.token
    _load_dotenv(args.env_file)
    token = os.environ.get(args.token_env) or os.environ.get("TEST_TOKEN")
    if not token:
        parser.error(
            "Token não encontrado. Passe --token, ou defina a env "
            f"{args.token_env} (ou TEST_TOKEN) no ambiente ou no .env."
        )
    return token


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args)
    config = load_config(args, parser)
    token = resolve_token(args, parser)

    # O token é injetado na env; a própria API (src.ballchasing_api) resolve o
    # header de autorização a partir dela — não precisamos passá-lo adiante.
    os.environ[api.TOKEN_ENV] = token

    downloader = Downloader(config, args.data_dir)
    downloader.run(once=args.once)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
