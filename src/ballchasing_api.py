import os

import requests

API_URL = "https://ballchasing.com/api"
TIMEOUT = 30

# O header de autorização é resolvido aqui mesmo, direto da env — nenhuma
# chamada precisa mais receber o token como parâmetro.
TOKEN_ENV = "BALLCHASING_TOKEN"


def resolve_token() -> str:
    """Lê o token da env (BALLCHASING_TOKEN, com fallback para TEST_TOKEN)."""
    token = os.environ.get(TOKEN_ENV) or os.environ.get("TEST_TOKEN")
    if not token:
        raise RuntimeError(
            f"Token da Ballchasing não encontrado. Defina a env {TOKEN_ENV} "
            "(ou TEST_TOKEN) antes de usar a API."
        )
    return token


def get_headers(authorization: str | None = None) -> dict:
    """Monta o header de autorização. Sem `authorization`, resolve da env."""
    if authorization is None:
        authorization = resolve_token()
    return {"Authorization": authorization}


def get_ping(authorization: str | None = None) -> requests.Response:
    return requests.get(API_URL, headers=get_headers(authorization), timeout=TIMEOUT)


def get_replay(replay_id: str, authorization: str | None = None) -> requests.Response:
    return requests.get(
        f"{API_URL}/replays/{replay_id}",
        headers=get_headers(authorization),
        timeout=TIMEOUT,
    )


def get_replays(authorization: str | None = None, filters: dict | None = None) -> requests.Response:
    return requests.get(
        f"{API_URL}/replays",
        headers=get_headers(authorization),
        params=filters,
        timeout=TIMEOUT,
    )

