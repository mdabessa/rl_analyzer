import json


def get_constants():
    with open("src/constants.json", encoding="utf-8") as f:
        return json.load(f)


def save_constants(constants):
    with open("src/constants.json", "w", encoding="utf-8") as f:
        json.dump(constants, f, indent=4)


CONSTANTS = get_constants()

RANKS = CONSTANTS["ranks"]

FEATURES_NAMES = [
    "shots",
    "shots_against",
    "goals",
    "goals_against",
    "saves",
    "assists",
    "score",
    "shooting_percentage",
    "bpm",
    "bcpm",
    "avg_amount",
    "amount_collected",
    "amount_stolen",
    "amount_collected_big",
    "amount_stolen_big",
    "amount_collected_small",
    "amount_stolen_small",
    "count_collected_big",
    "count_stolen_big",
    "count_collected_small",
    "count_stolen_small",
    "amount_overfill",
    "amount_overfill_stolen",
    "amount_used_while_supersonic",
    "percent_zero_boost",
    "percent_full_boost",
    "percent_boost_0_25",
    "percent_boost_25_50",
    "percent_boost_50_75",
    "percent_boost_75_100",
    "avg_speed",
    "total_distance",
    "time_powerslide",
    "count_powerslide",
    "avg_powerslide_duration",
    "avg_speed_percentage",
    "percent_slow_speed",
    "percent_boost_speed",
    "percent_supersonic_speed",
    "percent_ground",
    "percent_low_air",
    "percent_high_air",
    "avg_distance_to_ball",
    "avg_distance_to_ball_possession",
    "avg_distance_to_ball_no_possession",
    "avg_distance_to_mates",
    "percent_defensive_third",
    "percent_offensive_third",
    "percent_neutral_third",
    "percent_defensive_half",
    "percent_offensive_half",
    "percent_behind_ball",
    "percent_infront_ball",
    "percent_most_back",
    "percent_most_forward",
    "percent_closest_to_ball",
    "percent_farthest_from_ball",
    "inflicted",
    "taken",
]
