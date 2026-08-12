"""Arquivo de estado global (``state.json``): tracking de progresso.

Serve como o "cabeçalho" de progresso para monitorar e retomar o download.
A fonte da verdade para retomada são os manifests por bucket (IDs + página);
aqui fica um resumo agregado + timestamps.
"""

from __future__ import annotations

import time
from pathlib import Path

from .storage import Bucket, atomic_write_json, read_json


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


class State:
    def __init__(self, data_dir: str | Path) -> None:
        self.path = Path(data_dir) / "state.json"
        self.data = self._load()

    def _load(self) -> dict:
        data = read_json(self.path)
        if data is None:
            data = {
                "version": 1,
                "started_at": _now(),
                "updated_at": None,
                "buckets": {},
                "totals": {"manifest": 0, "downloaded": 0},
            }
        return data

    def set_bucket(self, bucket: Bucket, info: dict) -> None:
        self.data["buckets"][bucket.key()] = info

    def bucket_info(self, bucket: Bucket) -> dict:
        return self.data["buckets"].get(bucket.key(), {})

    def save(self) -> None:
        self.data["updated_at"] = _now()
        buckets = self.data["buckets"].values()
        self.data["totals"] = {
            "manifest": sum(b.get("manifest", 0) for b in buckets),
            "downloaded": sum(b.get("downloaded", 0) for b in buckets),
        }
        atomic_write_json(self.path, self.data)
