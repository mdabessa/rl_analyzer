from typing import List
import pandas as pd

from .constants import FEATURES_NAMES


def extract_players(replays: List[dict]) -> pd.DataFrame:
    players = []
    for replay in replays:
        # Estimate the rank tier of the match
        max_rank = replay["max_rank"]["tier"]
        min_rank = replay["min_rank"]["tier"]
        tier = int((max_rank + min_rank) / 2)

        winner = (
            "blue"
            if replay["blue"]["stats"]["core"]["goals"]
            > replay["orange"]["stats"]["core"]["goals"]
            else "orange"
        )
        replay["winner"] = winner
        c = 0
        for team in ["blue", "orange"]:
            for player in replay[team]["players"]:
                player["number"] = str(c)
                player["team"] = team
                player["tier"] = tier

                c += 1
                player_ = {
                    key: var
                    for tag in player["stats"]
                    for key, var in player["stats"][tag].items()
                    if key in FEATURES_NAMES
                }

                if len(player_) == len(FEATURES_NAMES):
                    player_["tier"] = tier
                    player_["id"] = replay["id"] + "-" + player["number"]
                    player_["start_time"] = player["start_time"]
                    player_["end_time"] = player["end_time"]

                    players.append(player_)

    df = pd.DataFrame(players)
    df.set_index(["id"], inplace=True)
    return df
