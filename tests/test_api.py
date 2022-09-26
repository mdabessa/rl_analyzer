import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

from http import HTTPStatus
from environs import Env
from time import sleep

import pytest
from fastapi.testclient import TestClient

from src.main import app


env = Env()
env.read_env()

TOKEN = os.environ["TEST_TOKEN"]


@pytest.fixture
def client():
    return TestClient(app)


def test_root_status_code(client):
    r = client.get("/")
    assert r.status_code == HTTPStatus.OK


def test_missing_token(client):
    sleep(2)
    response = client.get("/replay/c40c34dc-4949-4384-b899-4e1192f2debd")
    assert response.status_code == HTTPStatus.UNAUTHORIZED


def test_predict_key_in_json_response(client):
    sleep(2)
    response = client.get(
        "/replay/c40c34dc-4949-4384-b899-4e1192f2debd", headers={"Authorization": TOKEN}
    )
    assert "predict" in response.json()


def test_winner(client):
    sleep(2)
    response = client.get(
        "/replay/cb263873-1082-4b25-b5e0-fad9a2cb24eb", headers={"Authorization": TOKEN}
    )
    assert response.json()["winner"] == "blue"
