# blindchess

Practise blindfold chess in the terminal: play full games against Stockfish, or drill tactics,
position memory, board vision, endgames and openings. You type moves in standard algebraic
notation and the board stays hidden unless you peek.

## Setup

```bash
brew install stockfish zstd
python3 -m pip install --user chess
python3 fetch_data.py     # puzzles + openings into data/ (streams ~250 MB, keeps ~7 MB)
```

`fetch_data.py` keeps a random sample of 50,000 popular puzzles from the
[Lichess puzzle database](https://database.lichess.org/#puzzles) and the named opening lines from
[lichess-org/chess-openings](https://github.com/lichess-org/chess-openings) (both public domain).
Only the tactics, memory and opening drills need this data.

## Play a game

```bash
python3 blindchess.py                   # White, skill level 3
python3 blindchess.py -l 0              # easiest skill level (0-20)
python3 blindchess.py -e 1500 -c black  # play Black against a 1500-Elo Stockfish
```

| Flag | Meaning |
| --- | --- |
| `-l`, `--level` | Stockfish skill level 0-20 (default 3) |
| `-e`, `--elo` | Limit strength to an Elo rating (1320-3190) instead of `--level` |
| `-c`, `--color` | `white`, `black` or `random` (default `white`) |
| `-t`, `--think` | Engine thinking time per move in seconds (default 0.3) |

Commands during a game (also in endgames):

| Command | What it does |
| --- | --- |
| `e4`, `Nf3`, `O-O`, `e8=Q`, ... | Your move in SAN (UCI like `e2e4` also works) |
| `moves` | Show the game so far |
| `peek [s]` | Show status and board for `s` seconds (default 3), then hide it again |
| `board` | Show status and board and leave it on screen |
| `pieces` | List where all pieces stand, as text |
| `legal` | List your legal moves |
| `undo` | Take back your last move and the engine's reply |
| `fen` | Print the position as FEN |
| `resign` / `quit` | End the game |

`peek` and `board` count as peeks; the total is shown when the game ends.

## Training drills

All drills are in `train.py`; `python3 train.py <mode> -h` lists every option.

### Tactics

```bash
python3 train.py tactics                  # 10 puzzles near your rating, board shown 3 s
python3 train.py tactics -s 5 --theme fork
python3 train.py tactics -s 0             # true blindfold: pieces as text only
python3 train.py tactics --retry-missed
```

You see the board briefly, are told what the opponent just played, then type the solution move by
move; the opponent's replies are played for you. Any mate also counts. Your puzzle rating goes up
or down like Elo. `peek`, `pieces` and `hint` are allowed but the puzzle then counts as "with help"
(no rating change, kept for retry); `solution` and `skip` count as failed.

Themes include `fork`, `pin`, `skewer`, `mateIn1`, `mateIn2`, `mateIn3`, `discoveredAttack`,
`sacrifice`, `hangingPiece`, `endgame`, `middlegame`.

### Position memory

```bash
python3 train.py memory                   # 5 positions with 4-10 pieces, shown 5 s
python3 train.py memory -s 10 --max-pieces 16
```

After the board disappears, type each side's pieces, e.g. `Ke1 Qd1 Rf1 Nc3 e4 f2` (piece letters
in capitals, pawns as just the square). You get a score and a list of what you missed.

### Board vision

```bash
python3 train.py vision                   # 20 mixed questions
python3 train.py vision --types color,knight
```

Quick questions, timed: square colours (`color`), fewest knight moves (`knight`), all squares a
knight attacks (`knightsquares`), whether a piece reaches a square (`reach`), shared diagonals
(`diagonal`) and bishop routes (`bishop`).

### Endgames

```bash
python3 train.py endgame --list
python3 train.py endgame krk              # random king + rook vs king position
python3 train.py endgame kbnk -c black
python3 train.py endgame philidor --hold 20
```

You play against full-strength Stockfish. Generated positions (`kqk`, `krk`, `kbbk`, `kbnk`,
`kqkr`) are random but checked to be winning; `kpk`, `lucena` and `philidor` are the classic
positions. Winning endgames must end in checkmate before the 50-move rule; in `philidor` you defend
and must hold for `--hold` moves.

### Openings

```bash
python3 train.py opening --list sicilian
python3 train.py opening --name "Italian Game"
python3 train.py opening --name "Sicilian Defense: Najdorf" -c black -n 3
python3 train.py opening --eco C6 --continue    # play on vs Stockfish after the book
```

The book plays varied replies from every line matching your filter (main lines more often); you
must answer with book moves from memory. A wrong move shows the book moves and counts as a mistake;
`book` shows them on request (also a mistake).

### Progress

```bash
python3 train.py stats
```

Results are saved locally in `data/stats.json`.
