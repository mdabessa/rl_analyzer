from __future__ import annotations
import os

import joblib
import pandas as pd


class Model:
    def __init__(self, playlist: str) -> None:
        self.playlist_id = playlist

        if not os.path.exists("models"):
            file = os.path.join("../models", f"{playlist}.joblib")
        else:
            file = os.path.join("models", f"{playlist}.joblib")

        if not os.path.exists(file):
            raise FileNotFoundError(f"Model {playlist} not found!")

        model = joblib.load(file)
        self.model = model["model"]
        self.features = model["features"]

        self.population = None

    @staticmethod
    def get_model(playlist: str) -> Model:
        if not os.path.exists("models"):
            files = os.listdir("../models")
        else:
            files = os.listdir("models")

        files = [file.split(".")[0] for file in files]

        if playlist not in files:
            return None

        return Model(playlist)

    def load_population(self) -> None:
        if self.population is not None:
            return

        if not os.path.exists("data"):
            file = os.path.join("../data", f"population.csv")
        else:
            file = os.path.join("data", f"population.csv")

        df = pd.read_csv(file)
        df = df[df["playlist_id"] == self.playlist_id]

        self.population = df

    def extract_players(self, replays: list[dict] | dict) -> pd.DataFrame:
        if isinstance(replays, dict):
            replays = [replays]

        teams = ["blue", "orange"]
        players = []

        for replay in replays:
            winner = (
                replay["blue"]["stats"]["core"]["goals"]
                > replay["orange"]["stats"]["core"]["goals"]
            )

            for team in teams:
                for player in replay[team]["players"]:
                    p = {
                        "replay_id": replay["id"],
                        "player_id": player["id"]["platform"]
                        + "."
                        + player["id"]["id"],
                        "date": replay["date"],
                        "playlist_id": replay["playlist_id"],
                        "team": team,
                        "tier": replay["min_rank"]["tier"],
                        "duration": replay["duration"],
                        "start_time": player["start_time"],
                        "end_time": player["end_time"],
                        "mvp": player["mvp"] if "mvp" in player else False,
                        "stats": player["stats"],
                        "winner": winner if team == "blue" else not winner,
                    }

                    p["id"] = p["replay_id"] + "." + p["player_id"]
                    players.append(p)

        df = pd.json_normalize(players)
        return df

    def predict(self, replays: list[dict] | dict) -> pd.DataFrame:
        if isinstance(replays, dict):
            replays = [replays]

        df_players = self.extract_players(replays)
        X = df_players[self.features]
        na = X.isna().sum()
        na = na[na > 3].index

        X = X.fillna(0)

        df_players["predict"] = self.model.predict(X).flatten()
        df_players["predict"] = df_players["predict"].round(0).astype(int)

        df_players.loc[na, "predict"] = None

        return df_players

    def ranking(self, row: pd.Series) -> pd.Series:
        players = self.population[self.population.tier == row.tier]
        players = pd.concat([players, row.to_frame().T], ignore_index=True)
        rank = players.rank(pct=True)
        return rank.iloc[-1]

    def analyze(self, replays: list[dict] | dict) -> None:
        if isinstance(replays, dict):
            replays = [replays]

        self.load_population()

        df_players = self.predict(replays)

        for replay in replays:
            players = [
                player
                for team in ["blue", "orange"]
                for player in replay[team]["players"]
            ]

            for player in players:
                player["id"] = (
                    replay["id"]
                    + "."
                    + player["id"]["platform"]
                    + "."
                    + player["id"]["id"]
                )

            for idx, row in df_players.iterrows():
                player = [player for player in players if row["id"] == player["id"]][0]

                player["predict"] = {}
                player["predict"]["tier"] = round(row.predict)
                player["predict"]["mvp"] = False
                if row.predict == None:
                    continue

                rank = self.ranking(row)

                tags = player["predict"]["tags"] = []

                # TAGs

                if player["stats"]["core"]["mvp"]:
                    tags.append(
                        {"name": "MVP", "description": "Highest score of the match!"}
                    )

                if row["winner"]:
                    tags.append(
                        {"name": "Winner", "description": "Winner of the match."}
                    )

                if row.predict - row.tier > 5:
                    tags.append(
                        {
                            "name": "Smurf ?",
                            "description": f"{row.predict - row.tier} tiers predicted above the real rank!",
                        }
                    )

                if rank["stats.core.goals"] > 0.85:
                    tags.append(
                        {
                            "name": "Striker",
                            "description": f'This player scored {int(row["stats.core.goals"])} goals!',
                        }
                    )

                if rank["stats.core.saves"] > 0.85:
                    tags.append(
                        {
                            "name": "Goalkeaper",
                            "description": f'This player saved {int(row["stats.core.saves"])} shots!',
                        }
                    )

                if rank["stats.core.assists"] > 0.85:
                    tags.append(
                        {
                            "name": "Playmaker",
                            "description": f'This player assisted {int(row["stats.core.assists"])} gols!',
                        }
                    )

            best_row = df_players.sort_values(
                ["predict", "stats.core.score"], ascending=[False, False]
            ).iloc[0]
            best_player = [
                player for player in players if best_row["id"] == player["id"]
            ][0]

            best_player["predict"]["mvp"] = True

            best_player["predict"]["tags"].append(
                {"name": "Analyzer MVP", "description": "Best player by analyzer!"}
            )

            winner = (
                "blue"
                if replay["blue"]["stats"]["core"]["goals"]
                > replay["orange"]["stats"]["core"]["goals"]
                else "orange"
            )

            replay["winner"] = winner
            replay["predict"] = {}
            replay["predict"]["tier"] = round(df_players["predict"].mean())
