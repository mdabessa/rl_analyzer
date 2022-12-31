import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

import pymongo

from src.pre_processing import extract_players


playlist = "ranked-doubles"

cluster = pymongo.MongoClient("mongodb://localhost:27017")
db = cluster.get_database("rl_guess")
ranked_doubles = db.get_collection(playlist)
players = extract_players(list(ranked_doubles.find()))

players.to_csv(f"./population/{playlist}.csv")
