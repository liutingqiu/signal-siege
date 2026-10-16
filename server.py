#!/usr/bin/env python3
"""Signal Siege: a tiny turn-based game with a browser and agent API."""

from __future__ import annotations

import json
import os
import secrets
import string
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
HOST = os.environ.get("SIGNAL_SIEGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("SIGNAL_SIEGE_PORT", "8080"))
GRID = 7
MAX_ACTIONS = 2
COLORS = ["coral", "teal", "gold", "violet"]
STARTS = [(0, 0), (6, 6), (0, 6), (6, 0)]
MATCHES: dict[str, "Match"] = {}
LOCK = threading.RLock()


def code(length: int = 6) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def clean_name(value: Any, fallback: str) -> str:
    text = " ".join(str(value or "").split())[:24]
    return text or fallback


class GameError(Exception):
    pass


class Match:
    def __init__(self, max_players: int = 2):
        self.id = uuid.uuid4().hex[:10]
        self.join_code = code()
        self.max_players = max(2, min(4, int(max_players)))
        self.players: list[dict[str, Any]] = []
        self.units: list[dict[str, Any]] = []
        self.turn = 0
        self.active_player: str | None = None
        self.status = "lobby"
        self.winner: str | None = None
        self.beacon_owner: str | None = None
        self.beacon_charge = 0
        self.log: list[str] = ["Match created. Capture the central beacon to win."]
        self.lock = threading.RLock()

    def add_player(self, name: str, bot: bool = False) -> dict[str, Any]:
        with self.lock:
            if self.status != "lobby":
                raise GameError("match has already started")
            if len(self.players) >= self.max_players:
                raise GameError("match is full")
            number = len(self.players) + 1
            player_id = f"p{number}-{secrets.token_hex(2)}"
            player = {
                "id": player_id,
                "name": clean_name(name, f"Player {number}"),
                "color": COLORS[number - 1],
                "bot": bool(bot),
                "score": 0,
                "actions": MAX_ACTIONS,
            }
            self.players.append(player)
            sx, sy = STARTS[number - 1]
            for index in range(3):
                if number == 1:
                    x, y = sx + index, sy
                elif number == 2:
                    x, y = sx - index, sy
                elif number == 3:
                    x, y = sx, sy - index
                else:
                    x, y = sx, sy + index
                self.units.append(
                    {
                        "id": f"{player_id}-u{index + 1}",
                        "playerId": player_id,
                        "name": f"{player['name'][:10]}-{index + 1}",
                        "x": x,
                        "y": y,
                        "hp": 2,
                    }
                )
            self.log.append(f"{player['name']} joined the match.")
            if len(self.players) >= 2:
                self.status = "active"
                self.turn = 1
                self.active_player = self.players[0]["id"]
                self.log.append(f"Turn 1: {self.players[0]['name']} moves first.")
            return player

    def player(self, player_id: str) -> dict[str, Any]:
        for item in self.players:
            if item["id"] == player_id:
                return item
        raise GameError("unknown playerId")

    def unit(self, unit_id: str) -> dict[str, Any]:
        for item in self.units:
            if item["id"] == unit_id:
                return item
        raise GameError("unknown unitId")

    def _active(self, player_id: str) -> dict[str, Any]:
        if self.status != "active":
            raise GameError("match is not active")
        if self.active_player != player_id:
            raise GameError("it is not this player's turn")
        return self.player(player_id)

    def _occupied(self, x: int, y: int, ignore: str | None = None) -> dict[str, Any] | None:
        return next(
            (u for u in self.units if u["id"] != ignore and u["x"] == x and u["y"] == y and u["hp"] > 0),
            None,
        )

    def _check_win(self) -> None:
        alive = {u["playerId"] for u in self.units if u["hp"] > 0}
        if len(alive) == 1 and self.players:
            self.winner = next(iter(alive))
            self.status = "finished"
            self.log.append(f"{self.player(self.winner)['name']} wins by outlasting the field.")
        elif self.beacon_charge >= 3 and self.beacon_owner:
            self.winner = self.beacon_owner
            self.status = "finished"
            self.log.append(f"{self.player(self.winner)['name']} wins the beacon.")

    def move(self, player_id: str, unit_id: str, action: str, x: int | None = None, y: int | None = None, target_id: str | None = None) -> None:
        with self.lock:
            player = self._active(player_id)
            if player.get("actions", MAX_ACTIONS) <= 0:
                raise GameError("no action points left; end the turn")
            unit = self.unit(unit_id)
            if unit["playerId"] != player_id or unit["hp"] <= 0:
                raise GameError("unit does not belong to this player")
            action = str(action or "move").lower()
            if action == "move":
                if x is None or y is None or not (0 <= int(x) < GRID and 0 <= int(y) < GRID):
                    raise GameError("move requires an in-bounds x and y")
                x, y = int(x), int(y)
                if abs(x - unit["x"]) + abs(y - unit["y"]) != 1:
                    raise GameError("units move one tile at a time")
                if self._occupied(x, y, unit["id"]):
                    raise GameError("that tile is occupied")
                unit["x"], unit["y"] = x, y
                self.log.append(f"{player['name']} moved {unit['name']}.")
            elif action == "attack":
                target = self.unit(str(target_id or ""))
                if target["playerId"] == player_id or target["hp"] <= 0:
                    raise GameError("target must be a live opposing unit")
                if abs(target["x"] - unit["x"]) + abs(target["y"] - unit["y"]) != 1:
                    raise GameError("attacks require an adjacent target")
                target["hp"] -= 1
                self.log.append(f"{player['name']} hit {target['name']}.")
                if target["hp"] <= 0:
                    self.log.append(f"{target['name']} was removed from the board.")
            elif action == "capture":
                if (unit["x"], unit["y"]) != (GRID // 2, GRID // 2):
                    raise GameError("capture requires a unit on the central beacon")
                self.beacon_owner = player_id
                self.beacon_charge += 1
                player["score"] += 1
                self.log.append(f"{player['name']} charged the beacon ({self.beacon_charge}/3).")
            else:
                raise GameError("action must be move, attack, or capture")
            player["actions"] = player.get("actions", MAX_ACTIONS) - 1
            self._check_win()

    def end_turn(self, player_id: str) -> None:
        with self.lock:
            self._active(player_id)
            current = self.player(player_id)
            current["actions"] = MAX_ACTIONS
            index = next(i for i, p in enumerate(self.players) if p["id"] == player_id)
            for offset in range(1, len(self.players) + 1):
                candidate = self.players[(index + offset) % len(self.players)]
                if any(u["playerId"] == candidate["id"] and u["hp"] > 0 for u in self.units):
                    self.active_player = candidate["id"]
                    self.turn += 1
                    candidate["actions"] = MAX_ACTIONS
                    self.log.append(f"Turn {self.turn}: {candidate['name']} moves.")
                    if candidate.get("bot"):
                        self._bot_turn(candidate["id"])
                    return
            self._check_win()

    def _bot_turn(self, player_id: str) -> None:
        """Give the built-in bot a deterministic legal turn, then pass onward."""
        if self.status != "active":
            return
        bot = self.player(player_id)
        center = (GRID // 2, GRID // 2)
        for _ in range(MAX_ACTIONS):
            if self.status != "active" or self.active_player != player_id:
                return
            units = [u for u in self.units if u["playerId"] == player_id and u["hp"] > 0]
            if not units:
                self._check_win()
                return
            unit = min(units, key=lambda u: abs(u["x"] - center[0]) + abs(u["y"] - center[1]))
            if (unit["x"], unit["y"]) == center:
                self.move(player_id, unit["id"], "capture")
                continue
            adjacent_enemy = next(
                (other for other in self.units
                 if other["playerId"] != player_id and other["hp"] > 0
                 and abs(other["x"] - unit["x"]) + abs(other["y"] - unit["y"]) == 1),
                None,
            )
            if adjacent_enemy:
                self.move(player_id, unit["id"], "attack", target_id=adjacent_enemy["id"])
                continue
            candidates = []
            if unit["x"] < center[0]:
                candidates.append((unit["x"] + 1, unit["y"]))
            elif unit["x"] > center[0]:
                candidates.append((unit["x"] - 1, unit["y"]))
            if unit["y"] < center[1]:
                candidates.append((unit["x"], unit["y"] + 1))
            elif unit["y"] > center[1]:
                candidates.append((unit["x"], unit["y"] - 1))
            candidates.extend(((unit["x"] + 1, unit["y"]), (unit["x"] - 1, unit["y"]),
                               (unit["x"], unit["y"] + 1), (unit["x"], unit["y"] - 1)))
            destination = next(
                ((x, y) for x, y in candidates if 0 <= x < GRID and 0 <= y < GRID and not self._occupied(x, y, unit["id"])),
                None,
            )
            if destination is None:
                break
            self.move(player_id, unit["id"], "move", x=destination[0], y=destination[1])
        if self.status == "active" and self.active_player == player_id:
            bot["actions"] = MAX_ACTIONS
            index = next(i for i, p in enumerate(self.players) if p["id"] == player_id)
            for offset in range(1, len(self.players) + 1):
                candidate = self.players[(index + offset) % len(self.players)]
                if any(u["playerId"] == candidate["id"] and u["hp"] > 0 for u in self.units):
                    self.active_player = candidate["id"]
                    self.turn += 1
                    candidate["actions"] = MAX_ACTIONS
                    self.log.append(f"Turn {self.turn}: {candidate['name']} moves.")
                    if candidate.get("bot"):
                        self._bot_turn(candidate["id"])
                    return

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "id": self.id,
                "joinCode": self.join_code,
                "status": self.status,
                "maxPlayers": self.max_players,
                "turn": self.turn,
                "activePlayer": self.active_player,
                "winner": self.winner,
                "players": [dict(p) for p in self.players],
                "units": [dict(u) for u in self.units if u["hp"] > 0],
                "beacon": {"x": GRID // 2, "y": GRID // 2, "owner": self.beacon_owner, "charge": self.beacon_charge},
                "log": self.log[-12:],
            }


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length > 100_000:
        raise GameError("request body is too large")
    raw = handler.rfile.read(length) if length else b"{}"
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GameError("body must be valid JSON") from exc
    if not isinstance(data, dict):
        raise GameError("body must be a JSON object")
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "SignalSiege/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"{self.address_string()} - {fmt % args}", flush=True)

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message}, status)

    def do_OPTIONS(self) -> None:
        self.send_json({"ok": True})

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path == "/api/health":
            self.send_json({"ok": True, "game": "signal-siege", "version": "1.0"})
            return
        if path == "/api/matches":
            with LOCK:
                rows = [m.state() for m in MATCHES.values() if m.status != "finished"]
            self.send_json({"matches": rows})
            return
        if path.startswith("/api/matches/"):
            match_id = path.split("/")[-1]
            with LOCK:
                match = MATCHES.get(match_id)
            if not match:
                self.send_error_json("match not found", 404)
                return
            self.send_json({"match": match.state()})
            return
        if path in {"/", "/index.html"}:
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/sample_bot.py":
            body = (ROOT / "sample_bot.py").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error_json("not found", 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            data = read_json(self)
            if path == "/api/matches":
                match = Match(data.get("maxPlayers", 2))
                with LOCK:
                    MATCHES[match.id] = match
                self.send_json({"match": match.state()})
                return
            parts = path.split("/")
            if len(parts) < 4 or parts[1] != "api" or parts[2] != "matches":
                self.send_error_json("not found", 404)
                return
            with LOCK:
                match = MATCHES.get(parts[3])
            if not match:
                self.send_error_json("match not found", 404)
                return
            action = parts[4] if len(parts) > 4 else ""
            if action == "join":
                player = match.add_player(data.get("name", ""), bool(data.get("bot")))
                self.send_json({"player": player, "match": match.state()})
                return
            if action == "bot":
                player = match.add_player(data.get("name", "Atlas Bot"), True)
                self.send_json({"player": player, "match": match.state()})
                return
            if action == "move":
                match.move(str(data.get("playerId", "")), str(data.get("unitId", "")), str(data.get("action", "move")), data.get("x"), data.get("y"), data.get("targetId"))
                self.send_json({"match": match.state()})
                return
            if action == "end-turn":
                match.end_turn(str(data.get("playerId", "")))
                self.send_json({"match": match.state()})
                return
            self.send_error_json("unknown match action", 404)
        except GameError as exc:
            self.send_error_json(str(exc), 409)
        except (TypeError, ValueError) as exc:
            self.send_error_json(str(exc), 400)
        except Exception as exc:  # pragma: no cover - last-resort HTTP guard
            self.send_error_json(f"server error: {type(exc).__name__}", 500)


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Signal Siege listening on http://{HOST}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
