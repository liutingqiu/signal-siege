# Signal Siege

Signal Siege is a small, turn-based multiplayer strategy game for humans and AI agents. Two to four players move three units around a 7x7 board, fight adjacent units, and compete to charge the central beacon three times.

## Play

```bash
python server.py
```

Open `http://127.0.0.1:8080/`, create a match, and add the Atlas bot. No login or installation is required for players.

## Agent API

```text
GET  /api/health
POST /api/matches                 {"maxPlayers": 2}
POST /api/matches/:id/join        {"name": "Bot"}
GET  /api/matches/:id
POST /api/matches/:id/move        {"playerId", "unitId", "action": "move", "x", "y"}
POST /api/matches/:id/move        {"playerId", "unitId", "action": "attack", "targetId"}
POST /api/matches/:id/move        {"playerId", "unitId", "action": "capture"}
POST /api/matches/:id/end-turn    {"playerId"}
```

`POST /api/matches/:id/bot` adds a bot player for quick demos. `sample_bot.py` reads state, walks toward the beacon, and makes one legal move.

## Verification

```bash
python -m unittest -v test_server.py
```
