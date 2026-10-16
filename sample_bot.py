#!/usr/bin/env python3
"""Minimal agent client for Signal Siege.

Usage:
  python sample_bot.py http://127.0.0.1:8080 MATCH_ID PLAYER_ID
"""

from __future__ import annotations

import json
import sys
import urllib.request


def request(url: str, payload: dict | None = None) -> dict:
    if payload is None:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.loads(response.read())
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read())


def choose_move(state: dict, player_id: str) -> dict | None:
    units = [u for u in state["units"] if u["playerId"] == player_id]
    if not units:
        return None
    center = state["beacon"]
    unit = min(units, key=lambda u: abs(u["x"] - center["x"]) + abs(u["y"] - center["y"]))
    if (unit["x"], unit["y"]) == (center["x"], center["y"]):
        return {"playerId": player_id, "unitId": unit["id"], "action": "capture"}
    dx = 1 if unit["x"] < center["x"] else -1 if unit["x"] > center["x"] else 0
    dy = 1 if unit["y"] < center["y"] else -1 if unit["y"] > center["y"] else 0
    return {"playerId": player_id, "unitId": unit["id"], "action": "move", "x": unit["x"] + dx, "y": unit["y"] + dy}


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    base, match_id, player_id = sys.argv[1:]
    state = request(f"{base.rstrip('/')}/api/matches/{match_id}")["match"]
    if state["activePlayer"] != player_id:
        print("not this bot's turn")
        return
    move = choose_move(state, player_id)
    if move:
        print(json.dumps(request(f"{base.rstrip('/')}/api/matches/{match_id}/move", move), indent=2))


if __name__ == "__main__":
    main()
