import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

from collections import defaultdict
from joblib import load
from random import sample

from src.analyzer import analyzer
from src.db import database
from src.pre_processing import extract_players
from src.ranking import Ranking


playlist = "ranked-doubles"
collection = database.get_collection(f'{playlist}-test')

replays = list(collection.find())
ranking = Ranking(extract_players(collection.find({})))

# Replays sample
replays = sample(replays, 300)

print("Loading model...")
model = load(f"./src/ml_models/{playlist}.joblib")

print(f"Analyzing {len(replays)} replays...")
analyzer(model, replays, ranking)


print("Evaluating...")

total_players = 0
predict_players = 0
replay_accuracy = 0
players_accuracy = 0
mvp_accuracy = 0
smurfs = []
tags = defaultdict(int)

for replay in replays:
    max_rank = replay["max_rank"]["tier"]
    min_rank = replay["min_rank"]["tier"]
    tier = int((max_rank + min_rank) / 2)

    if replay["predict"]["tier"] == tier:
        replay_accuracy += 1

    for team in ["orange", "blue"]:
        for player in replay[team]["players"]:
            total_players += 1

            if "predict" not in player:
                continue

            predict_players += 1

            if player["predict"]["tier"] == player["tier"]:
                players_accuracy += 1

            if ((player["predict"]["mvp"] == True) and (player["stats"]["core"]["mvp"] == True)):
                mvp_accuracy += 1

            for tag in player["predict"]["tags"]:
                tags[tag["name"]] += 1
            
            match player:
                case {"predict": {"tags": [{"name": "Smurf ?"}]}}:
                    smurfs.append((replay['id'], player))


tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)

print(f"Predicted players / Total players: {(predict_players/total_players)*100:.2f}%")
print(f"Replay tier predict accuracy: {replay_accuracy/len(replays)*100:.2f}%")
print(f"Player tier predict accuracy: {players_accuracy/predict_players*100:.2f}%")
print(f"MVP predict accuracy: {mvp_accuracy/predict_players*100:.2f}%")

print()
print("=== Tags ===")
for name, value in tags:
    perc = (value / predict_players) * 100
    print(f"{name}: {value:5} ({perc:.2f}%)")


print()
print("=== Smurfs Sample ===")
for smurf in smurfs[:3]:
    print(
        f'id: {smurf[0]}\n',
        f'player: {smurf[1]["name"]}\n',
        f'rank: {smurf[1]["tier"]}\n',
        f'predict: {smurf[1]["predict"]["tier"]}\n',
        f'predict tags: {smurf[1]["predict"]["tags"]}\n',
        f'predict mvp: {smurf[1]["predict"]["mvp"]}\n',
        f'Link: https://ballchasing.com/replay/{smurf[0]}\n'
    )
