import pymongo


cluster = pymongo.MongoClient("mongodb://localhost:27017/")
db = cluster.get_database("rl_guess")

ranked_duels = db.get_collection("ranked-duels")
ranked_doubles = db.get_collection("ranked-doubles")
