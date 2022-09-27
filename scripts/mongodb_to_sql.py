import os
import sys

sys.path.append(os.path.join(os.path.dirname(sys.path[0])))

import pymongo
import sqlite3 as sql

from src.preprocessing import extract_players


# MongoDB connection
cluster = pymongo.MongoClient("mongodb://localhost:27017")
db = cluster.get_database("rl_guess")
ranked_doubles = db.get_collection("ranked-doubles")

# Sqlite connection
connection = sql.connect("./database/database.db")


players = extract_players(list(ranked_doubles.find()))

players.to_sql("ranked_doubles", connection, if_exists="replace")
