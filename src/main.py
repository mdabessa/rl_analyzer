from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from joblib import load

from .analyzer import analyzer
from .ballchasing_api import get_replay
from .db import ranked_doubles
from .preprocessing import extract_players
from .ranking import Ranking


population_doubles = extract_players(ranked_doubles.find({}))

models = {
    "ranked-doubles": {
        "ranking": Ranking(population_doubles),
        "model": load("./src/ml_models/ranked_doubles.joblib"),
    }
}

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

    if replay["playlist_id"] not in models:
        raise HTTPException(
            status_code=400, detail=f"Replay playlist is not compatible."
        )

    model = models[replay["playlist_id"]]
    analyzer(model["model"], [replay], model["ranking"])

    return replay
