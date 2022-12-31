from typing import List

from .pre_processing import extract_players
from .ranking import Ranking


def analyzer(model, replays: List[dict], ranking: Ranking) -> None:
    df_players = extract_players(replays)
    df_players["predict"] = model.predict(df_players.drop(["tier"], axis=1)).flatten()

    for replay in replays:
        players = [
            player for team in ["blue", "orange"] for player in replay[team]["players"]
        ]

        df_replay = df_players[df_players.index.str.startswith(replay["id"])]
        for idx, row in df_replay.iterrows():
            rank = ranking.ranking(row)
            player = [player for player in players if idx.endswith(player["number"])][0]
            player["predict"] = {}
            player["predict"]["tier"] = round(row.predict)
            player["predict"]["mvp"] = False

            tags = player["predict"]["tags"] = []

            # TAGs

            if player["stats"]["core"]["mvp"]:
                tags.append(
                    {"name": "MVP", "description": "Highest score of the match!"}
                )

            if player["team"] == replay["winner"]:
                tags.append({"name": "Winner", "description": "Winner of the match."})

            if row.predict - row.tier > 5:
                tags.append(
                    {
                        "name": "Smurf ?",
                        "description": f"This player are {round(row.predict) - row.tier} tiers lower from the predict rank!",
                    }
                )

            if rank.goals > 0.85:
                tags.append(
                    {
                        "name": "Striker",
                        "description": f"This player scored {int(row.goals)} goals!",
                    }
                )

            if rank.saves > 0.85:
                tags.append(
                    {
                        "name": "Goalkeaper",
                        "description": f"This player saved {int(row.saves)} shots!",
                    }
                )

            if rank.assists > 0.85:
                tags.append(
                    {
                        "name": "Playmaker",
                        "description": f"This player assisted {int(row.assists)} gols!",
                    }
                )

        best_row = df_replay.sort_values(
            ["predict", "score"], ascending=[False, False]
        ).iloc[0]
        best_player = [
            player for player in players if best_row.name.endswith(player["number"])
        ][0]

        best_player["predict"]["mvp"] = True

        best_player["predict"]["tags"].append(
            {"name": "Analyzer MVP", "description": "Best player by analyzer!"}
        )

        replay["predict"] = {}
        replay["predict"]["tier"] = round(df_replay["predict"].mean())
