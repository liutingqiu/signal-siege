import json
import threading
import unittest
import urllib.request

from server import Handler, Match, ThreadingHTTPServer


class SignalSiegeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.thread.join(timeout=2)

    def call(self, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        req = urllib.request.Request(self.base + path, body, {"Content-Type": "application/json"} if body else {})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())

    def test_health_and_match_lifecycle(self):
        self.assertTrue(self.call("/api/health")["ok"])
        created = self.call("/api/matches", {"maxPlayers": 2})["match"]
        first = self.call(f"/api/matches/{created['id']}/join", {"name": "Human"})
        second = self.call(f"/api/matches/{created['id']}/bot", {"name": "Atlas"})
        self.assertEqual(second["match"]["status"], "active")
        player = first["player"]["id"]
        unit = next(u for u in second["match"]["units"] if u["playerId"] == player and u["x"] == 0 and u["y"] == 0)
        self.call(f"/api/matches/{created['id']}/move", {"playerId": player, "unitId": unit["id"], "action": "move", "x": unit["x"], "y": unit["y"] + 1})
        state = self.call(f"/api/matches/{created['id']}")["match"]
        self.assertEqual(state["activePlayer"], player)
        self.call(f"/api/matches/{created['id']}/end-turn", {"playerId": player})
        state = self.call(f"/api/matches/{created['id']}")["match"]
        self.assertEqual(state["activePlayer"], player)
        self.assertTrue(any("Atlas" in line and "moved" in line for line in state["log"]))

    def test_move_rules(self):
        match = Match(2)
        p1 = match.add_player("A")["id"]
        match.add_player("B")
        unit = next(u for u in match.units if u["playerId"] == p1)
        with self.assertRaises(Exception):
            match.move(p1, unit["id"], "move", 6, 6)


if __name__ == "__main__":
    unittest.main()
