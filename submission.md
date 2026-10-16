Signal Siege public game: http://43.153.18.165/
Repository: https://github.com/liutingqiu/signal-siege

Signal Siege is a compact, polished turn-based strategy game for humans and agents. Humans play in the browser with no login; agents use the documented HTTP/JSON API and the included sample bot. Each player has two actions per turn, must decide between positioning, attacking, and beacon control, and the match ends when the beacon is charged three times or one side is eliminated.

Highlights:
- 2-4 player lobby with match ID and a built-in Atlas bot.
- Browser board with responsive layout, player colors, turn state, score, beacon charge, and event log.
- JSON API for match creation, joining, state reads, moves, attacks, captures, and turn changes.
- Focused Python tests for the API lifecycle and movement rules.
