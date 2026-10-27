# blindchess

Practise blindfold chess against Stockfish in the terminal. You type moves in standard
algebraic notation, Stockfish replies, and the board stays hidden unless you peek.

## Setup

```bash
brew install stockfish
python3 -m pip install --user chess
```

## Play

```bash
python3 blindchess.py                 # White, skill level 3
python3 blindchess.py -l 0            # easiest skill level (0-20)
python3 blindchess.py -e 1500 -c black  # play Black against a 1500-Elo Stockfish
```

Options:

| Flag | Meaning |
| --- | --- |
| `-l`, `--level` | Stockfish skill level 0-20 (default 3) |
| `-e`, `--elo` | Limit strength to an Elo rating (1320-3190) instead of `--level` |
| `-c`, `--color` | `white`, `black` or `random` (default `white`) |
| `-t`, `--think` | Engine thinking time per move in seconds (default 0.3) |

## Commands during a game

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
