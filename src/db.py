import pymongo


cluster = pymongo.MongoClient("mongodb://localhost:27017/")
database = cluster.get_database("rl_guess")

"""
# Duel
ranked_duels = db.get_collection("ranked-duels")

# Doubles
ranked_doubles = db.get_collection("ranked-doubles")
ranked_doubles_test = db.get_collection("ranked-doubles-test")
ranked_doubles_train = db.get_collection("ranked-doubles-train")

# Standard
ranked_standard = db.get_collection("ranked-standard")
"""