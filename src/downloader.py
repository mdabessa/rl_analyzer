"""Orquestra o download de replays da Ballchasing para um data lake em pastas.

Estratégia (round-robin com paginação estável):

- Cada passada avança **1 página** (``count``) em cada bucket
  (season/playlist/tier) não esgotado, mantendo os buckets com tamanhos iguais.
- A paginação é feita sobre um **manifest local de IDs** (estável): a API só é
  consultada para crescer o bucket; no restart não se re-gasta queries de list
  em páginas já processadas.
- A dedup por arquivo (existência de ``<id>.json``) evita re-baixar detalhes.
- Quando todos os buckets esgotam, o loop dorme ``rescan_interval`` e re-procura
  por replays novos (modo infinito).
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path

import requests

from . import ballchasing_api as api
from .constants import RANKS
from .state import State
from .storage import (
    Bucket,
    load_manifest,
    replay_exists,
    save_manifest,
    save_replay,
)

logger = logging.getLogger(__name__)


class RateLimiter:
    """Janela deslizante: no máximo ``per_hour`` requisições por hora."""

    def __init__(self, per_hour: float) -> None:
        self.per_hour = max(1.0, float(per_hour))
        self._times: list[float] = []

    def wait(self) -> None:
        now = time.time()
        window_start = now - 3600.0
        self._times = [t for t in self._times if t > window_start]
        if len(self._times) >= self.per_hour:
            sleep_until = self._times[0] + 3600.0
            if sleep_until > now:
                time.sleep(sleep_until - now)
            now = sleep_until
        self._times.append(now)


class Downloader:
    def __init__(self, config: dict, data_dir: str | Path) -> None:
        self.config = config
        self.data_dir = Path(data_dir)
        self.limiter = RateLimiter(config.get("rate_limit_per_hour", 490))
        self.stop_event = threading.Event()
        self.state = State(self.data_dir)
        self.count = int(config.get("count", 200))
        self.max_retries = int(config.get("max_retries", 5))
        self.retry_backoff = float(config.get("retry_backoff", 5.0))
        self.rescan_interval = float(config.get("rescan_interval", 1800))
        self.buckets = self._build_buckets()
        self._install_signal_handlers()


    def _build_buckets(self) -> list[Bucket]:
        seasons = self.config["seasons"]
        playlists = self.config["playlists"]
        tiers = self.config["tiers"]
        start, end = int(tiers["start"]), int(tiers["end"])
        if not (0 <= start <= end <= len(RANKS) - 1):
            raise ValueError(f"Faixa de tiers inválida: {start}..{end}")
        return [
            Bucket(season=s, playlist=p, tier=t)
            for s in seasons
            for p in playlists
            for t in range(start, end + 1)
        ]

    def _install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._on_signal)
        signal.signal(signal.SIGTERM, self._on_signal)

    def _on_signal(self, signum, frame) -> None:
        logger.info("Sinal %s recebido — encerrando graciosamente...", signum)
        self.stop_event.set()


    def _rank(self, bucket: Bucket) -> str:
        return RANKS[bucket.tier]

    def _list_filters(self, bucket: Bucket, page: int) -> dict:
        filters = {
            "count": self.count,
            "page": page,
            "playlist": bucket.playlist,
            "min-rank": self._rank(bucket),
            "max-rank": self._rank(bucket),
            "season": bucket.season,
            "sort-by": self.config.get("sort_by", "replay-date"),
            "sort-dir": self.config.get("sort_dir", "asc"),
        }
        pro = self.config.get("pro")
        if pro is not None:
            filters["pro"] = str(pro).lower()
        return filters

    def _request(self, do_request, what: str, fatal: bool):
        """Executa a requisição com rate-limit e retry/backoff exponencial.

        - ``fatal=True`` (list): falha persistente levanta exceção (aborta o run).
        - ``fatal=False`` (detail): após esgotar retries, retorna ``None``; o
          replay fica pendente no manifest e é retomado na próxima passada.
        """
        last_error = None
        for attempt in range(self.max_retries):
            self.limiter.wait()
            if self.stop_event.is_set():
                raise InterruptedError("download interrompido")
            try:
                resp = do_request()
            except requests.RequestException as exc:
                last_error = exc
                retryable = True
                logger.warning(
                    "%s — erro de rede: %s (tentativa %d/%d)",
                    what, exc, attempt + 1, self.max_retries,
                )
            else:
                if resp.status_code == 200:
                    return resp
                retryable = resp.status_code == 429 or resp.status_code >= 500
                if retryable:
                    logger.warning(
                        "%s — status %d (tentativa %d/%d)",
                        what, resp.status_code, attempt + 1, self.max_retries,
                    )
                else:
                    logger.error("%s — status %d: %s", what, resp.status_code, resp.text[:200])
                    if fatal:
                        resp.raise_for_status()
                    return None

            if retryable:
                time.sleep(self.retry_backoff * (2**attempt))

        if fatal:
            suffix = f": {last_error}" if last_error else ""
            raise RuntimeError(f"{what} falhou após {self.max_retries} tentativas{suffix}")
        return None

    def fetch_list(self, bucket: Bucket, page: int) -> list[dict]:
        # O header é resolvido dentro da API (src.ballchasing_api) via env.
        resp = self._request(
            lambda: api.get_replays(filters=self._list_filters(bucket, page)),
            f"list {bucket.key()} p{page}",
            fatal=True,
        )
        if resp is None:  # fatal=True nunca retorna None, mas protege o type-checker
            raise RuntimeError(f"list {bucket.key()} p{page}: resposta nula")

        return resp.json().get("list", [])

    def fetch_detail(self, replay_id: str) -> dict | None:
        resp = self._request(
            lambda: api.get_replay(replay_id),
            f"replay {replay_id}",
            fatal=False,
        )
        return None if resp is None else resp.json()


    def process_bucket(self, bucket: Bucket) -> str:
        """Avança um bucket em 1 página e baixa pendentes.

        Retorna ``"progressed"`` (ainda há dados) ou ``"exhausted"`` (fim do bucket).
        """
        manifest = load_manifest(self.data_dir, bucket)
        if manifest.get("rank") is None:
            manifest["rank"] = self._rank(bucket)
            save_manifest(self.data_dir, bucket, manifest)

        # Retoma downloads pendentes de passadas anteriores/restart.
        self._download_pending(bucket, manifest)

        if manifest.get("exhausted"):
            self._update_state(bucket, manifest)
            return "exhausted"

        next_page = manifest.get("page", 0) + 1
        replays = self.fetch_list(bucket, next_page)

        known = set(manifest["ids"])
        added = 0
        for replay in replays:
            rid = replay.get("id")
            if not rid or rid in known:
                continue
            manifest["ids"].append(rid)
            known.add(rid)
            added += 1

        manifest["page"] = next_page
        if len(replays) < self.count:
            manifest["exhausted"] = True
        if added == 0 and not manifest.get("exhausted"):
            logger.warning(
                "%s — página %d não adicionou IDs novos (drift na ordenação?)",
                bucket.key(), next_page,
            )
        save_manifest(self.data_dir, bucket, manifest)

        self._download_pending(bucket, manifest)
        self._update_state(bucket, manifest)
        return "exhausted" if manifest.get("exhausted") else "progressed"

    def _download_pending(self, bucket: Bucket, manifest: dict) -> int:
        """Baixa os detalhes dos IDs do manifest que ainda não existem no disco."""
        downloaded = 0
        for rid in manifest["ids"]:
            if self.stop_event.is_set():
                break
            if replay_exists(self.data_dir, bucket, rid):
                continue
            detail = self.fetch_detail(rid)
            if detail is None:
                continue
            save_replay(self.data_dir, bucket, rid, detail)
            downloaded += 1
            logger.debug("%s — baixou %s", bucket.key(), rid)
        return downloaded

    def _count_downloaded(self, bucket: Bucket, manifest: dict) -> int:
        return sum(
            1 for rid in manifest["ids"] if replay_exists(self.data_dir, bucket, rid)
        )

    def _update_state(self, bucket: Bucket, manifest: dict) -> None:
        self.state.set_bucket(
            bucket,
            {
                "rank": manifest.get("rank"),
                "page": manifest.get("page", 0),
                "manifest": len(manifest["ids"]),
                "downloaded": self._count_downloaded(bucket, manifest),
                "exhausted": manifest.get("exhausted", False),
            },
        )
        self.state.save()


    def run(self, once: bool = False) -> None:
        logger.info(
            "Downloader iniciado: %d buckets, data_dir=%s",
            len(self.buckets), self.data_dir,
        )
        if once:
            logger.info("Modo --once ativado (apenas uma passada).")

        while not self.stop_event.is_set():
            active = False
            for bucket in self.buckets:
                if self.stop_event.is_set():
                    break
                try:
                    result = self.process_bucket(bucket)
                except InterruptedError:
                    break
                except Exception:
                    if self.stop_event.is_set():
                        break
                    logger.exception("Erro fatal ao processar bucket %s", bucket.key())
                    raise
                if result == "progressed":
                    active = True

            if once:
                break

            if not active:
                if self.rescan_interval <= 0:
                    logger.info("Todos os buckets esgotados e rescan desligado. Encerrando.")
                    break
                logger.info(
                    "Nenhum bucket ativo — dormindo %.0fs e depois re-procurando novos replays...",
                    self.rescan_interval,
                )
                self._sleep_interruptible(self.rescan_interval)
                self._rearm_exhausted()

        self.state.save()
        logger.info("Downloader encerrado.")

    def _rearm_exhausted(self) -> None:
        """Re-habilita buckets esgotados para sondar replays novos na próxima passada."""
        for bucket in self.buckets:
            manifest = load_manifest(self.data_dir, bucket)
            if manifest.get("exhausted"):
                manifest["exhausted"] = False
                save_manifest(self.data_dir, bucket, manifest)

    def _sleep_interruptible(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end and not self.stop_event.is_set():
            time.sleep(min(1.0, max(0.0, end - time.time())))
