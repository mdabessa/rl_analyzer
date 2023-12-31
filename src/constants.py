import json


def get_constants():
    with open("src/constants.json", encoding="utf-8") as f:
        return json.load(f)


def save_constants(constants):
    with open("src/constants.json", "w", encoding="utf-8") as f:
        json.dump(constants, f, indent=4)


CONSTANTS = get_constants()

RANKS = CONSTANTS["ranks"]
