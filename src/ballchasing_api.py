import requests


def get_ping(authorization: str) -> requests.Response:
    ping_url = "https://ballchasing.com/api"
    ping = requests.get(ping_url, headers={"Authorization": authorization})
    return ping


def get_replay(replay_id: str, authorization: str) -> requests.Response:
    replay_url = "https://ballchasing.com/api/replays/" + str(replay_id)
    replay = requests.get(replay_url, headers={"Authorization": authorization})
    return replay


def get_replays(authorization: str, filters: dict = None) -> requests.Response:
    replays = requests.get("https://ballchasing.com/api/replays", headers={"Authorization": authorization}, 
                    params=filters)
    return replays

