"""
    Explore the features of the dataset and select the most common ones to use in the model.
"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

from collections import defaultdict
from pprint import pprint

from src.constants import get_constants, save_constants
from src.db import database


playlist = "ranked-doubles"
min_ = 0.95

collection = database.get_collection(f"{playlist}")
replays = list(collection.find())

features = defaultdict(int)

for replay in replays:
    for team in ["orange", "blue"]:
        for player in replay[team]["players"]:
            for tag in player["stats"]:
                for key, var in player["stats"][tag].items():
                    features[key] += 1


players = len(replays) * len(replays[0]["blue"]["players"]) * 2
features = {key: var / players for key, var in features.items()}
features = sorted(features.items(), key=lambda x: x[1], reverse=True)

print(f"Total replays: {len(replays)}")
print(f'Total players: {players}')
print(f"Total features: {len(features)}")
pprint(features)

features = [key for key, var in features if var >= min_]

print(f"Features with more than {min_ * 100}% of the players: {len(features)}")

constants = get_constants()

if "features" not in constants:
    constants["features"] = {}

constants["features"][playlist] = features

save_constants(constants)
