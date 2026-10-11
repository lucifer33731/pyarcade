"""High-score table saved to highscores.json next to the game."""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "highscores.json")
MAX_ENTRIES = 5

# Starter scores so the table is never empty. Beat them!
SEEDS = {
    "invaders": [("CPU", 3000), ("ZED", 2000), ("KAT", 1200), ("BOB", 800), ("AAA", 400)],
    "drift": [("CPU", 6500), ("ZED", 5200), ("KAT", 4200), ("BOB", 3200), ("AAA", 2200)],
}
DEFAULT_SEED = [("CPU", 3000), ("ZED", 2000), ("KAT", 1200), ("BOB", 800), ("AAA", 400)]


def _load():
    try:
        with open(PATH, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def top(game_id):
    entries = _load().get(game_id)
    if not entries:
        entries = [{"name": n, "score": s} for n, s in SEEDS.get(game_id, DEFAULT_SEED)]
    return sorted(entries, key=lambda e: -e["score"])[:MAX_ENTRIES]


def qualifies(game_id, score):
    entries = top(game_id)
    return score > 0 and (len(entries) < MAX_ENTRIES or score > entries[-1]["score"])


def add(game_id, name, score):
    """Insert a score; returns its rank index (0 = best)."""
    entry = {"name": name, "score": int(score)}
    entries = sorted(top(game_id) + [entry], key=lambda e: -e["score"])[:MAX_ENTRIES]
    data = _load()
    data[game_id] = entries
    try:
        with open(PATH, "w") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass
    return entries.index(entry) if entry in entries else -1
