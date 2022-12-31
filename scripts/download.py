import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

import requests
from tqdm import tqdm
import time
from environs import Env

from src.db import database
from src.constants import RANKS

env = Env()
env.read_env()

TOKEN = os.environ["TEST_TOKEN"] # Ballchasing token
HEADERS = {"Authorization": TOKEN}

URL = "https://ballchasing.com/api/replays"
TIERS = range(14, 22)  # Tiers to populates database (highest tier = 21)
PLAYLIST = "ranked-duels"
SEASON = 'f7'
QT = 200  # Amount per tier (max = 200)
LIMIT_RATE_PER_HOUR = 490

collection = database.get_collection(PLAYLIST)

delay = 3600 / LIMIT_RATE_PER_HOUR
time_exp = delay * QT * len(TIERS)
print(
    f"Time expected: {int(time_exp/3600)}:{int((time_exp%3600)/60)}:{int((time_exp%3600)%60)}"
)
for tier in TIERS:
    rank = RANKS[tier]
    print(f"Starting {rank}[{tier}] rank!")

    filters = {"count": QT, "playlist": PLAYLIST, "min-rank": rank, "max-rank": rank, 'season': SEASON}

    response = requests.get(URL, headers=HEADERS, params=filters)

    if response.status_code != 200:
        print(f"Response error: {response}")
        break

    replays = response.json()["list"]
    data = tqdm(replays, desc=f"{rank}[{tier}]")
    for d in data:
        time.sleep(delay)

        replay_url = d["link"]

        response = requests.get(replay_url, headers=HEADERS)
        if response.status_code != 200:
            continue

        replay = response.json()
        if replay["status"] != "ok":
            continue
        
        rep = collection.find_one({'id': replay['id']})
        if rep is None:
            collection.insert_one(replay)


    print(f"{rank}[{tier}] done!")
