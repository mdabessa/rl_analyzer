"""Auditoria de qualidade: bronze/manifests vs arquivos (stubs, buracos, órfãos).

Lê direto do sistema de arquivos (``data/replays`` + ``data/manifests``),
sem depender do warehouse — é a camada de "checagem de dados" que o Superset
não faz.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.storage import Bucket, load_manifest, replays_dir  # noqa: E402

MIN_FILE_SIZE = 300  # abaixo disso = suspeito de stub


def _bucket_from_manifest_path(path: Path) -> Bucket | None:
    """Extrai o Bucket do caminho .../season=<s>/playlist=<p>/tier=<t>/manifest.json."""
    kv = {}
    for p in path.parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k] = v
    if {"season", "playlist", "tier"} <= kv.keys():
        return Bucket(kv["season"], kv["playlist"], int(kv["tier"]))
    return None


def audit(data_dir) -> pd.DataFrame:
    """Por bucket: manifest × arquivos, pendentes, órfãos, skipped, exhausted."""
    data_dir = Path(data_dir)
    rows = []
    manifests_root = data_dir / "manifests"
    for m_path in sorted(manifests_root.rglob("manifest.json")):
        bucket = _bucket_from_manifest_path(m_path)
        if bucket is None:
            continue
        manifest = load_manifest(data_dir, bucket)
        ids = set(manifest["ids"])
        skipped = set(manifest.get("skipped", []))
        rdir = replays_dir(data_dir, bucket)
        files = {p.stem for p in rdir.glob("*.json")} if rdir.exists() else set()

        rows.append(
            {
                "season": bucket.season,
                "playlist": bucket.playlist,
                "tier": bucket.tier,
                "manifest": len(ids),
                "files": len(files),
                "downloaded": len(ids & files),
                "pending": len(ids - files - skipped),
                "skipped": len(skipped),
                "orphans": len(files - ids),
                "exhausted": manifest.get("exhausted", False),
                "last_date": manifest.get("last_date"),
            }
        )
    return pd.DataFrame(rows)


def detect_stubs(data_dir, deep: bool = False) -> pd.DataFrame:
    """Arquivos de replay suspeitos (muito pequenos ou JSON inválido)."""
    data_dir = Path(data_dir)
    bad = []
    for p in (data_dir / "replays").rglob("*.json"):
        size = p.stat().st_size
        if size < MIN_FILE_SIZE:
            bad.append(
                {"file": str(p.relative_to(data_dir)), "size": size, "issue": "tamanho < mínimo"}
            )
            continue
        if deep:
            try:
                json.loads(p.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                bad.append(
                    {"file": str(p.relative_to(data_dir)), "size": size, "issue": f"JSON inválido: {exc}"}
                )
    return pd.DataFrame(bad)
