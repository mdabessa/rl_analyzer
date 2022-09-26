import requests


def get_replay(replay_id: str, authorization: str) -> requests.Response:
    replay_url = "https://ballchasing.com/api/replays/" + str(replay_id)
    replay = requests.get(replay_url, headers={"Authorization": authorization})
    return replay
