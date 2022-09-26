import pandas as pd


class Ranking:
    def __init__(self, population: pd.DataFrame) -> None:
        self.players_by_tier = {}
        for i in range(1, 23):
            self.players_by_tier[i] = population[population.tier == i]

    def ranking(
        self,
        row: pd.Series,
    ) -> pd.Series:
        players = self.players_by_tier[row.tier].append(row, ignore_index=True)
        rank = players.rank(pct=True)
        return rank.iloc[-1]
