"""Camada Silver (medallion): bronze (JSONs crus) -> Parquet colunar particionado.

Lê os JSONs do bronze com DuckDB e escreve duas tabelas Parquet (silver),
particionadas por ``season/playlist_id/tier`` (estilo Hive):

- ``replays``: 1 linha por replay. Campos do topo + ``min_rank``/``max_rank`` +
  ``server``/``uploader`` + estatísticas de *time* (``blue.*``/``orange.*``).
- ``players``: 1 linha por jogador por replay (base para ML/população). Todos os
  campos do player (``id.*``, ``rank.*``, ``camera.*``, ``stats.*``, ...) +
  colunas de contexto (``replay_id``, ``season``, ``playlist_id``, ``tier``,
  ``team``).

Schema dinâmico
---------------
Em vez de listar atributos à mão, o schema é **descoberto de uma amostra** do
bronze (padrão 1000 replays) e cada folha vira uma coluna achatada por domínio:
objetos aninhados viram colunas com o caminho separado por ``.``
(ex.: ``{"a": {"b": 4, "c": {"d": 0}}}`` -> colunas ``a.b`` e ``a.c.d``).

- Folhas vistas em >= ``min_presence`` das linhas da amostra são "comuns" e
  viram colunas. Campos comuns que faltarem num replay/player específico viram
  **NULL**.
- Folhas raras (abaixo do limiar, ex.: ``recorder``, ``id.player_number``) são
  **ignoradas** — evita dezenas de colunas quase sempre vazias.
- Listas são ignoradas (não viram coluna), exceto ``blue.players`` /
  ``orange.players`` que alimentam a tabela ``players``.

A leitura usa ``read_json`` do DuckDB com schema explícito (gerado a partir das
folhas descobertas): campos ausentes viram NULL e chaves extras são ignoradas sem
erro de binding. ``hive_partitioning=false`` garante leitura do conteúdo do JSON
(as pastas ``season=f12/.../tier=0`` usam índice 0-based e não devem vazar). Na
escrita, ``WRITE_PARTITION_COLUMNS true`` grava ``season/playlist_id/tier``
também dentro de cada arquivo Parquet (Parquet autodescritivo), então nenhuma
leitura downstream depende de inferência Hive das pastas.

Incremental e leve (roda em background, ex.: Airflow)
-----------------------------------------------------
Pensado para rodar periodicamente sem travar a máquina:

- **Sem threads próprias** e com o DuckDB limitado a poucos threads
  (``SET threads=2``). Cada COPY processa **um bucket por vez**
  (``data/replays/season=S/playlist=P/tier=T``, ~centenas de arquivos), então o
  pico de CPU/memória é pequeno.
- **Incremental por replay id**: arquivos cujo ``<id>.json`` já está no Parquet
  são pulados. Só o que é novo é processado (append em arquivos ``append_*.parquet``
  dentro da partição, sem reescrever o que já existe).
- **Rebuild total só quando muda o schema**: um fingerprint (hash das colunas
  descobertas + tipo) é guardado em ``<out_dir>/silver_state.json``. Se o schema
  descoberto mudou — ou os parâmetros (``sample_size``/``min_presence``) — faz
  rebuild completo (bucket a bucket numa pasta temporária e troca atômica no
  fim). Senão, só os replays novos entram.
- Estado de "quais ids já foram gravados" é derivado do próprio Parquet
  (coluna ``replay_id``), sem arquivo extra de ids.

Depende apenas de DuckDB (sem pandas/pyarrow). A descoberta usa só a stdlib.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
from pathlib import Path

import duckdb

DEFAULT_SAMPLE_SIZE = 1000  # replays sorteados para descobrir o schema
DEFAULT_MIN_PRESENCE = 0.01  # folha vira coluna se presente em >= 1% das linhas
DEFAULT_SEED = 0  # semente fixa -> fingerprint estável entre execuções

_THREADS = 2  # limite p/ o DuckDB (roda em background; evita travar a máquina)
_COMPACT_AFTER = 64  # nº de arquivos por partição que dispara compactação
_STATE_FILE = "silver_state.json"

# Folhas do topo do replay que são substituídas por colunas de identidade:
#   id          -> replay_id  (nome mais claro, usado p/ cruzar com ``players``)
#   season      -> normalizado ("f12"): a API devolve int (12) ou string ("f12")
#   playlist_id -> mesma coluna de partição (nome/valor idênticos)
_ID_REPLACED = ("id", "season", "playlist_id")

# Normaliza a temporada: a API pode devolver inteiro (12) ou string ("f12").
SEASON_SQL = (
    "CASE WHEN CAST(season AS VARCHAR) LIKE 'f%' "
    "THEN CAST(season AS VARCHAR) "
    "ELSE 'f' || CAST(season AS VARCHAR) END"
)

_TABLES = (("replays",), ("players",))


# --------------------------------------------------------------------------- #
# Descoberta de schema (stdlib, SEM threads)
# --------------------------------------------------------------------------- #
def _flatten(obj: dict, prefix: str = ""):
    """Gera ``(caminho_pontilhado, valor)`` para cada folha escalar de ``obj``.

    Dicionários são percorridos; listas são ignoradas (não viram coluna).
    """
    for key, value in obj.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten(value, path)
        elif not isinstance(value, list):
            yield path, value


def _kind(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def _ducktype(kinds: set[str]) -> str:
    """Tipo DuckDB de uma folha a partir dos kinds vistos na amostra."""
    if not kinds or kinds == {"str"}:
        return "VARCHAR"
    if kinds == {"bool"}:
        return "BOOLEAN"
    if kinds == {"int"}:
        return "BIGINT"
    if kinds <= {"int", "float"}:  # só números (int e/ou float) -> DOUBLE
        return "DOUBLE"
    return "VARCHAR"  # tipo misto (ex.: season int|str) -> VARCHAR


def _parse_one(path: str) -> tuple[int, set, dict, dict, dict]:
    """Abre e achata um replay.

    Retorna ``(n_players, rep_paths, rep_kinds, play_counts, play_kinds)``:
    - ``n_players``: nº de jogadores (azul + laranja) no replay;
    - ``rep_paths``: folhas presentes no replay (presença = 1 replay);
    - ``rep_kinds``: path -> kinds vistos (valores não-nulos) no replay;
    - ``play_counts``: path -> nº de players que têm aquela folha (p/ presença);
    - ``play_kinds``: path -> kinds vistos entre os players.
    """
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    rep_paths: set[str] = set()
    rep_kinds: dict[str, set[str]] = {}
    play_counts: dict[str, int] = {}
    play_kinds: dict[str, set[str]] = {}
    n_players = 0

    for p, v in _flatten(doc):
        rep_paths.add(p)
        if v is not None:
            rep_kinds.setdefault(p, set()).add(_kind(v))

    for team in ("blue", "orange"):
        players = doc.get(team, {}).get("players", []) or []
        for player in players:
            n_players += 1
            for p, v in _flatten(player):
                play_counts[p] = play_counts.get(p, 0) + 1
                if v is not None:
                    play_kinds.setdefault(p, set()).add(_kind(v))

    return n_players, rep_paths, rep_kinds, play_counts, play_kinds


def _discover_leaves(
    files: list[Path],
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    min_presence: float = DEFAULT_MIN_PRESENCE,
    seed: int = DEFAULT_SEED,
):
    """Amostra o bronze (sequencial) e devolve as folhas comuns + metadados."""
    rng = random.Random(seed)
    chosen = rng.sample(files, min(sample_size, len(files)))

    rep_present: dict[str, int] = {}
    rep_kinds: dict[str, set[str]] = {}
    play_present: dict[str, int] = {}
    play_kinds: dict[str, set[str]] = {}
    n_replays = 0
    n_players = 0

    for f in chosen:  # sem threads: simples e leve
        try:
            np_, rp, rk, pc, pk = _parse_one(str(f))
        except (OSError, json.JSONDecodeError, KeyError):
            continue  # arquivo corrompido/incompleto não conta na amostra
        n_replays += 1
        n_players += np_
        for p in rp:
            rep_present[p] = rep_present.get(p, 0) + 1
        for p, kinds in rk.items():
            rep_kinds.setdefault(p, set()).update(kinds)
        for p, count in pc.items():
            play_present[p] = play_present.get(p, 0) + count
        for p, kinds in pk.items():
            play_kinds.setdefault(p, set()).update(kinds)

    def keep(cnt: dict[str, int], kinds: dict[str, set[str]], n: int):
        threshold = min_presence * n
        kept = sorted(
            (p, _ducktype(kinds[p])) for p, c in cnt.items() if c >= threshold
        )
        dropped = sorted(p for p, c in cnt.items() if c < threshold)
        return kept, dropped

    replay_leaves, dropped_replay = keep(rep_present, rep_kinds, n_replays)
    player_leaves, dropped_player = keep(play_present, play_kinds, n_players)
    return replay_leaves, player_leaves, {
        "n_replays": n_replays,
        "n_players": n_players,
        "dropped_replay": dropped_replay,
        "dropped_player": dropped_player,
    }


# --------------------------------------------------------------------------- #
# Schema de leitura (aninhado) para o DuckDB
# --------------------------------------------------------------------------- #
def _paths_to_tree(paths: list[tuple[str, str]]) -> dict:
    """``[(a.b, BIGINT), ...]`` -> dict aninhado espelhando a estrutura JSON.

    Folha = str (tipo DuckDB); objeto intermediário = dict.
    """
    root: dict = {}
    for dot, typ in paths:
        node = root
        segments = dot.split(".")
        for seg in segments[:-1]:
            child = node.get(seg)
            if child is None:
                child = {}
                node[seg] = child
            elif isinstance(child, str):
                raise ValueError(f"conflito folha/objeto em '{dot}'")
            node = child
        node[segments[-1]] = typ
    return root


def _dtype(node) -> str:
    """Gera a string de tipo DuckDB a partir da árvore aninhada."""
    if isinstance(node, str):
        return node
    fields = ", ".join(f"{key} {_dtype(child)}" for key, child in node.items())
    return f"STRUCT({fields})"


def _leaf_exprs(alias: str, paths: list[str]) -> list[str]:
    """``alias.<a.b.c> AS "a.b.c"`` para cada caminho (colunas pontilhadas)."""
    return [f'{alias}.{p} AS "{p}"' for p in paths]


def _replays_sql(files: list[Path], replay_leaves: list[tuple[str, str]]):
    """Monta o COPY da tabela ``replays``. Retorna (sql, [files], columns)."""
    leaf_paths = sorted(p for p, _ in replay_leaves if p not in _ID_REPLACED)

    # Árvore de leitura: folhas de replay + topo p/ derivar id/season/playlist.
    tree = dict(_paths_to_tree(replay_leaves))
    tree["id"] = "VARCHAR"
    tree["season"] = "VARCHAR"
    tree["playlist_id"] = "VARCHAR"
    columns = {key: _dtype(child) for key, child in tree.items()}

    season_sql = SEASON_SQL.replace("season", "r.season")
    select = [
        'CAST(r.id AS VARCHAR) AS "replay_id"',
        f'{season_sql} AS "season"',
        'r.playlist_id AS "playlist_id"',
        'CAST(r.min_rank.tier AS BIGINT) AS "tier"',
    ]
    select += _leaf_exprs("r", leaf_paths)

    sql = (
        f"SELECT {', '.join(select)}\n"
        "FROM read_json(?, columns=?, hive_partitioning=false) AS r"
    )
    return sql, [str(f) for f in files], columns


def _players_sql(files: list[Path], player_leaves: list[tuple[str, str]]):
    """Monta o COPY da tabela ``players``. Retorna (sql, [files], columns)."""
    leaf_paths = sorted(p for p, _ in player_leaves)

    # Leitura: topo (id/season/playlist_id/min_rank.tier) + arrays dos times.
    elem = dict(_paths_to_tree(player_leaves))
    elem_type = _dtype(elem)
    columns = {
        "id": "VARCHAR",
        "season": "VARCHAR",
        "playlist_id": "VARCHAR",
        "min_rank": "STRUCT(tier BIGINT)",
        "blue": f"STRUCT(players {elem_type}[])",
        "orange": f"STRUCT(players {elem_type}[])",
    }

    season_sql = SEASON_SQL.replace("season", "rp.season")
    select = ["replay_id", "season", "playlist_id", "tier", "team"]
    select += _leaf_exprs("p", leaf_paths)

    sql = (
        "WITH base AS (\n"
        "    SELECT CAST(rp.id AS VARCHAR) AS replay_id,\n"
        f"           {season_sql} AS season,\n"
        "           rp.playlist_id AS playlist_id,\n"
        "           CAST(rp.min_rank.tier AS BIGINT) AS tier,\n"
        "           t.team_name AS team,\n"
        "           u.p AS p\n"
        "    FROM read_json(?, columns=?, hive_partitioning=false) AS rp\n"
        "    CROSS JOIN (VALUES ('blue'), ('orange')) AS t(team_name)\n"
        "    CROSS JOIN LATERAL (\n"
        "        SELECT UNNEST(CASE t.team_name\n"
        "            WHEN 'blue' THEN rp.blue.players\n"
        "            ELSE rp.orange.players END) AS p\n"
        "    ) AS u\n"
        ")\n"
        f"SELECT {', '.join(select)} FROM base"
    )
    return sql, [str(f) for f in files], columns


def _builder_for(table: str):
    """Retorna o builder de SQL/colunas conforme a tabela."""
    return _replays_sql if table == "replays" else _players_sql


def _leaves_for(table: str, replay_leaves, player_leaves):
    return replay_leaves if table == "replays" else player_leaves


def _copy(con, sql, sql_files, columns, dest_root: Path) -> None:
    """Executa um COPY particionado para ``dest_root`` (pasta já deve existir).

    ``WRITE_PARTITION_COLUMNS true`` grava ``season/playlist_id/tier`` TAMBÉM
    dentro de cada arquivo Parquet, além da pasta. Assim nenhuma leitura
    downstream depende da inferência Hive das pastas (folder tier é 0-based no
    bronze e nunca deve vazar; aqui os valores são sempre os do conteúdo).
    """
    con.execute(
        f"COPY ({sql}) TO '{dest_root}' "
        "(FORMAT PARQUET, PARTITION_BY (season, playlist_id, tier), "
        "OVERWRITE_OR_IGNORE, WRITE_PARTITION_COLUMNS true)",
        [sql_files, columns],
    )


# --------------------------------------------------------------------------- #
# Estado / ids existentes
# --------------------------------------------------------------------------- #
def _schema_fingerprint(replay_leaves, player_leaves) -> str:
    payload = json.dumps(
        {"replay": replay_leaves, "player": player_leaves}, sort_keys=True
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _load_state(out_dir: Path) -> dict | None:
    path = out_dir / _STATE_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_state(out_dir: Path, state: dict) -> None:
    path = out_dir / _STATE_FILE
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _existing_replay_ids(con, out_dir: Path) -> set[str] | None:
    """Ids já gravados no Parquet (None se não existe Parquet ainda)."""
    replays = out_dir / "replays"
    if not replays.is_dir() or not any(replays.rglob("*.parquet")):
        return None
    rows = con.execute(
        f"SELECT DISTINCT replay_id FROM read_parquet('{replays}/**/*.parquet')"
    ).fetchall()
    return {r[0] for r in rows}


def _count_parquet(con, out_dir: Path, table: str) -> int:
    root = out_dir / table
    if not root.is_dir() or not any(root.rglob("*.parquet")):
        return 0
    row = con.execute(
        f"SELECT count(*) FROM read_parquet('{root}/**/*.parquet')"
    ).fetchone()
    return row[0] if row else 0


# --------------------------------------------------------------------------- #
# Bronze -> buckets
# --------------------------------------------------------------------------- #
def _bronze_folders(data_dir: Path) -> tuple[list[tuple[Path, list[Path]]], int]:
    """Agrupa os JSONs legíveis por bucket (pasta season/playlist/tier).

    Retorna ``(buckets, unreadable)`` onde cada bucket é ``(pasta, [arquivos])``.
    """
    root = data_dir / "replays"
    if not root.is_dir():
        raise FileNotFoundError(f"Sem bronze em: {root}")

    by_folder: dict[Path, list[Path]] = {}
    unreadable = 0
    for path in root.rglob("*.json"):
        if not path.is_file():
            continue
        # os.access é um stat (barato); não precisa abrir 171k arquivos
        if os.access(path, os.R_OK):
            by_folder.setdefault(path.parent, []).append(path)
        else:
            unreadable += 1

    buckets = sorted((folder, sorted(files)) for folder, files in by_folder.items())
    return buckets, unreadable


# --------------------------------------------------------------------------- #
# Rebuild total (bucket a bucket numa pasta temporária + troca atômica)
# --------------------------------------------------------------------------- #
def _full_rebuild(
    con,
    buckets: list[tuple[Path, list[Path]]],
    replay_leaves,
    player_leaves,
    out_dir: Path,
) -> None:
    tmp = out_dir / ".rebuild_tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    (tmp / "replays").mkdir(parents=True)
    (tmp / "players").mkdir(parents=True)
    n = len(buckets)
    try:
        for i, (folder, files) in enumerate(buckets, 1):
            if not files:
                continue
            for table in ("replays", "players"):
                sql, sql_files, columns = _builder_for(table)(
                    files, _leaves_for(table, replay_leaves, player_leaves)
                )
                _copy(con, sql, sql_files, columns, tmp / table)
            if i % 25 == 0 or i == n:
                print(f"  rebuild ... {i}/{n} buckets", flush=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise

    # troca atômica: substitui as árvores antigas pelas novas
    for table in ("replays", "players"):
        final = out_dir / table
        shutil.rmtree(final, ignore_errors=True)
        os.replace(tmp / table, final)
    shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Append incremental (só os replays novos)
# --------------------------------------------------------------------------- #
def _delta_append(
    con,
    bucket_new: list[tuple[Path, list[Path]]],
    replay_leaves,
    player_leaves,
    out_dir: Path,
) -> tuple[int, int]:
    """Grava apenas os arquivos novos, adicionando arquivos à partição."""
    total_rep = 0
    total_play = 0
    for idx, (folder, files) in enumerate(bucket_new):
        if not files:
            continue
        print(
            f"  +{len(files):,} replays novos em {folder.parent.name}/"
            f"{folder.name}",
            flush=True,
        )
        for table in ("replays", "players"):
            sql, sql_files, columns = _builder_for(table)(
                files, _leaves_for(table, replay_leaves, player_leaves)
            )
            staging = out_dir / f".append_tmp_{table}"
            shutil.rmtree(staging, ignore_errors=True)
            staging.mkdir(parents=True)
            _copy(con, sql, sql_files, columns, staging)

            # conta o que foi gravado (para o log)
            row = con.execute(
                f"SELECT count(*) FROM read_parquet('{staging}/**/*.parquet')"
            ).fetchone()
            if table == "replays":
                total_rep += row[0] if row else 0
            else:
                total_play += row[0] if row else 0

            # move os arquivos produzidos para dentro das partições finais,
            # sem sobrescrever o que já existia (nome único por append)
            for produced in sorted(staging.rglob("*.parquet")):
                rel = produced.relative_to(staging)
                target_dir = out_dir / table / rel.parent
                target_dir.mkdir(parents=True, exist_ok=True)
                existing = sorted(target_dir.glob("*.parquet"))
                dest = (
                    target_dir / "data_0.parquet"
                    if not existing
                    else target_dir / f"append_{idx}_{len(existing)}.parquet"
                )
                os.replace(produced, dest)
            shutil.rmtree(staging, ignore_errors=True)
    return total_rep, total_play


def _compact_partitions(con, out_dir: Path, table: str, max_files: int) -> int:
    """Junta partições com muitos arquivos pequenos em um único data_0.parquet."""
    root = out_dir / table
    if not root.is_dir():
        return 0
    compacted = 0
    parts = [
        d
        for d in root.rglob("*")
        if d.is_dir() and list(d.glob("*.parquet"))
    ]
    for part in parts:
        files = sorted(part.glob("*.parquet"))
        if len(files) <= max_files:
            continue
        staging = out_dir / ".compact_tmp"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        try:
            con.execute(
                f"COPY (SELECT * FROM read_parquet('{part}/*.parquet')) "
                f"TO '{staging}' (FORMAT PARQUET, "
                "PARTITION_BY (season, playlist_id, tier), "
                "OVERWRITE_OR_IGNORE, WRITE_PARTITION_COLUMNS true)"
            )
            produced = sorted(staging.rglob("*.parquet"))
            for f in files:
                f.unlink()
            for p in produced:
                rel = p.relative_to(staging)
                tdir = out_dir / table / rel.parent
                tdir.mkdir(parents=True, exist_ok=True)
                os.replace(p, tdir / "data_0.parquet")
            compacted += 1
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return compacted


# --------------------------------------------------------------------------- #
# Build (orquestração)
# --------------------------------------------------------------------------- #
def build_silver(
    data_dir: str | Path,
    out_dir: str | Path,
    *,
    sample_size: int = DEFAULT_SAMPLE_SIZE,
    min_presence: float = DEFAULT_MIN_PRESENCE,
    seed: int | None = None,
    force: bool = False,
) -> dict:
    """Sincroniza o Parquet silver com o bronze (incremental).

    Regras:
    - Arquivo cujo ``<id>.json`` já está no Parquet não é reprocessado.
    - Sem replays novos e schema inalterado -> não faz nada (rápido).
    - Schema mudou (fingerprint) ou ``--force`` -> rebuild total.
    - Senão -> só os replays novos entram (append por bucket).
    """
    data_dir = Path(data_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seed = DEFAULT_SEED if seed is None else seed

    buckets, unreadable = _bronze_folders(data_dir)
    all_files = [f for _, files in buckets for f in files]
    if not all_files:
        raise FileNotFoundError(
            f"Nenhum replay JSON legível em {data_dir / 'replays'}"
        )
    if unreadable:
        print(
            f"[aviso] {unreadable:,} arquivo(s) JSON ilegível(eis) por permissão"
            " — ignorados. Corrija com: chmod -R a+r data/replays",
            flush=True,
        )

    params = {"sample_size": sample_size, "min_presence": min_presence}
    state = _load_state(out_dir)

    con = duckdb.connect()
    con.execute(f"SET threads = {_THREADS}")
    summary = {
        "mode": None,
        "new_replays": 0,
        "appended_replays": 0,
        "appended_players": 0,
        "n_replays": 0,
        "n_players": 0,
    }
    try:
        existing = _existing_replay_ids(con, out_dir)
        replay_leaves = player_leaves = None

        # ---- decide o modo ----
        if existing is None or force or state is None or state.get("params") != params:
            mode = "full"
        else:
            new_files = [f for f in all_files if f.stem not in existing]
            if not new_files:
                print(
                    "Nada de novo no bronze e schema inalterado — nada a fazer.",
                    flush=True,
                )
                summary["mode"] = "noop"
                summary["n_replays"] = _count_parquet(con, out_dir, "replays")
                summary["n_players"] = _count_parquet(con, out_dir, "players")
                return summary
            replay_leaves, player_leaves, _meta = _discover_leaves(
                all_files, sample_size, min_presence, seed
            )
            if _schema_fingerprint(replay_leaves, player_leaves) == state.get(
                "fingerprint"
            ):
                mode = "delta"
            else:
                mode = "full"

        # ---- descobre o schema (rebuild) ----
        if replay_leaves is None:
            print(
                f"Descobrindo schema: amostra de até "
                f"{min(sample_size, len(all_files)):,} de {len(all_files):,} replays"
                f" (min_presence={min_presence:.0%}) ...",
                flush=True,
            )
            replay_leaves, player_leaves, meta = _discover_leaves(
                all_files, sample_size, min_presence, seed
            )
            print(
                f"  amostra: {meta['n_replays']:,} replays, "
                f"{meta['n_players']:,} players -> {len(replay_leaves)} colunas "
                f"replay, {len(player_leaves)} colunas player",
                flush=True,
            )
            if meta["dropped_replay"]:
                print(f"  folhas raras de replay ignoradas: {meta['dropped_replay']}")
            if meta["dropped_player"]:
                print(f"  folhas raras de player ignoradas: {meta['dropped_player']}")

        fingerprint = _schema_fingerprint(replay_leaves, player_leaves)

        # ---- executa ----
        if mode == "full":
            reason = (
                "rebuild total solicitado (--force)"
                if force
                else "primeiro build"
                if existing is None
                else "schema mudou (ou parâmetros alterados)"
            )
            print(f"Rebuild total: {reason} — {len(all_files):,} replays.", flush=True)
            _full_rebuild(con, buckets, replay_leaves, player_leaves, out_dir)
            n_rep = _count_parquet(con, out_dir, "replays")
            n_play = _count_parquet(con, out_dir, "players")
            print(f"  replays: {n_rep:,} | players: {n_play:,}", flush=True)
            summary["mode"] = "full"
            summary["n_replays"] = n_rep
            summary["n_players"] = n_play
        else:  # delta
            assert existing is not None  # só chega aqui com Parquet já existente
            new_by_bucket = [
                (folder, [f for f in files if f.stem not in existing])
                for folder, files in buckets
            ]
            new_by_bucket = [
                (folder, fs) for folder, fs in new_by_bucket if fs
            ]
            summary["new_replays"] = sum(len(fs) for _, fs in new_by_bucket)
            print(
                f"Append incremental: {summary['new_replays']:,} replays novos.",
                flush=True,
            )
            added_rep, added_play = _delta_append(
                con, new_by_bucket, replay_leaves, player_leaves, out_dir
            )
            summary["mode"] = "delta"
            summary["appended_replays"] = added_rep
            summary["appended_players"] = added_play
            summary["n_replays"] = _count_parquet(con, out_dir, "replays")
            summary["n_players"] = _count_parquet(con, out_dir, "players")
            print(
                f"  +{added_rep:,} replays | +{added_play:,} players "
                f"(total: {summary['n_replays']:,} / {summary['n_players']:,})",
                flush=True,
            )
            for table in ("replays", "players"):
                n = _compact_partitions(con, out_dir, table, _COMPACT_AFTER)
                if n:
                    print(f"  {table}: {n} partição(ões) compactada(s)", flush=True)

        _save_state(
            out_dir,
            {"fingerprint": fingerprint, "params": params, "seed": seed},
        )
    finally:
        con.close()

    assert replay_leaves is not None and player_leaves is not None
    summary["replay_columns"] = [p for p, _ in replay_leaves]
    summary["player_columns"] = [p for p, _ in player_leaves]
    return summary
