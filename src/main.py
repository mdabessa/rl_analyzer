from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import time

from .analyzer import Model
from .ballchasing_api import get_replay, get_ping, get_replays


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_credentials=False,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    return {"status": "ok"}


@app.get("/replay/{replay_id}")
async def replay(replay_id: str, authorization: str | None = Header(default=None)):
    if authorization is None:
        raise HTTPException(
            status_code=401, detail={"error": "Missing authorization token"}
        )

    response = get_replay(replay_id, authorization)
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=response.json())

    replay = response.json()

    model = Model.get_model(replay["playlist_id"])

    if model is None:
        raise HTTPException(
            status_code=400, detail=f"Replay playlist is not compatible."
        )

    model.analyze(replay)

    return replay


@app.get("/last")
async def last(authorization: str | None = Header(default=None)):
    if authorization is None:
        raise HTTPException(
            status_code=401, detail={"error": "Missing authorization token"}
        )

    ping = get_ping(authorization)
    ping.raise_for_status()

    time.sleep(0.5)

    replays = get_replays(authorization, filters={"player-name": ping.json()["name"], "count": 1})
    replays.raise_for_status()

    time.sleep(0.5)

    replay_id = replays.json()['list'][0]['id']

    time.sleep(0.5)

    response = get_replay(replay_id, authorization)
    response.raise_for_status()

    replay = response.json()

    model = Model.get_model(replay["playlist_id"])
    if model is None:
        raise HTTPException(
            status_code=400, detail=f"Replay playlist is not compatible."
        )
    
    model.analyze(replay)

    return replay
