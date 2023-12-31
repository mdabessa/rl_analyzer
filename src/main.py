from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware

from .analyzer import Model
from .ballchasing_api import get_replay


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
