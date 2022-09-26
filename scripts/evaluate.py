import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

from collections import defaultdict
from joblib import load
from pprint import pprint
from random import shuffle

from src.analyzer import analyzer
from src.db import ranked_doubles
from src.preprocessing import extract_players
from src.ranking import Ranking


replays = list(ranked_doubles.find())
population_doubles = extract_players(ranked_doubles.find({}))
ranking = Ranking(population_doubles)

# Replays sample
shuffle(replays)
replays = replays[:1000]

print("Loading model...")
model = load("./src/ml_models/ranked_doubles.joblib")

print(f"Analyzing {len(replays)} replays...")
analyzer(model, replays, ranking)


print("Evaluating...")
replay_accuracy = 0
total_players = 0
predict_players = 0
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

            for tag in player["predict"]["tags"]:
                tags[tag["name"]] += 1

tags = {tag: tags[tag] / predict_players for tag in tags}
tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)
tags = {key: f"{value*100:.2f}%" for key, value in tags}

print(f"Replay tier predict accuracy: {replay_accuracy/len(replays)*100:.2f}%")
print(f"Player tier predict accuracy: {(predict_players/total_players)*100:.2f}%")
pprint(tags)
