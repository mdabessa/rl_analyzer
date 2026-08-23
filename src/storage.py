"""Persistência em pastas: replays brutos, manifests por bucket e state.

Estrutura dentro de ``data_dir`` (ex.: uma pasta sincronizada no Nextcloud):

    data_dir/
    ├── replays/                          # detalhes brutos de cada replay
    │   └── season=<s>/playlist=<p>/tier=<t>/<replay_id>.json
    ├── manifests/                        # "catálogo" de IDs por bucket
    │   └── season=<s>/playlist=<p>/tier=<t>/manifest.json
    └── state.json                        # tracking global de progresso

O layout ``chave=valor`` por diretório segue o padrão de partição do Hive,
facilitando a leitura por Spark/Hive/DuckDB no futuro (simulação de Hadoop).
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bucket:
    """Uma combinação season/playlist/tier que define um 'bucket' de replays."""

    season: str
    playlist: str
    tier: int

    def key(self) -> str:
        return f"{self.season}/{self.playlist}/{self.tier}"

    def rel_dir(self) -> str:
        """Diretório relativo no formato particionado estilo Hive."""
        return f"season={self.season}/playlist={self.playlist}/tier={self.tier}"



def replays_dir(data_dir: Path, bucket: Bucket) -> Path:
    return Path(data_dir) / "replays" / bucket.rel_dir()


def manifests_dir(data_dir: Path, bucket: Bucket) -> Path:
    return Path(data_dir) / "manifests" / bucket.rel_dir()


def manifest_path(data_dir: Path, bucket: Bucket) -> Path:
    return manifests_dir(data_dir, bucket) / "manifest.json"


def state_path(data_dir: Path) -> Path:
    return Path(data_dir) / "state.json"



def atomic_write_json(path: Path, obj) -> None:
    """Escreve JSON de forma atômica (tmp + rename).

    Se o processo morrer no meio da escrita, o arquivo antigo fica intacto —
    essencial para o tracking de progresso.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def replay_path(data_dir: Path, bucket: Bucket, replay_id: str) -> Path:
    return replays_dir(data_dir, bucket) / f"{replay_id}.json"


def replay_exists(data_dir: Path, bucket: Bucket, replay_id: str) -> bool:
    return replay_path(data_dir, bucket, replay_id).exists()


def save_replay(data_dir: Path, bucket: Bucket, replay_id: str, data: dict) -> Path:
    path = replay_path(data_dir, bucket, replay_id)
    atomic_write_json(path, data)
    return path


def load_manifest(data_dir: Path, bucket: Bucket) -> dict:
    manifest = read_json(manifest_path(data_dir, bucket))
    if manifest is None:
        manifest = {
            "season": bucket.season,
            "playlist": bucket.playlist,
            "tier": bucket.tier,
            "rank": None,
            "page": 0,
            "last_date": None,
            "ids": [],
            "exhausted": False,
        }
    return manifest


def save_manifest(data_dir: Path, bucket: Bucket, manifest: dict) -> None:
    atomic_write_json(manifest_path(data_dir, bucket), manifest)
