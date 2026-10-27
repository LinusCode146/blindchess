"""Shared helpers for the blindfold chess tools."""
import json
import shutil
import sys
import time
from pathlib import Path

import chess
import chess.engine

DATA = Path(__file__).resolve().parent / "data"
STATS_FILE = DATA / "stats.json"

PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}
PIECE_ORDER = (chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN)

GAME_HELP = """Commands:
  <move>     your move in SAN (e4, Nf3, Bxc6+, O-O, e8=Q); UCI like e2e4 also works
  moves      show the game so far
  peek [s]   sneak peek: game status + board for s seconds (default 3), then hidden again
  board      show the board and leave it on screen
  pieces     list where all pieces stand, as text
  legal      list your legal moves
  undo       take back your last move and the engine's reply
  fen        print the position as FEN
  resign     give up
  quit       exit
  help       this text"""


# --- engine -----------------------------------------------------------------

def find_stockfish():
    path = shutil.which("stockfish")
    if not path:
        sys.exit("Stockfish not found. Install it with: brew install stockfish")
    return path


def open_engine(level=20, elo=None):
    """Start Stockfish and return (engine, description of its strength)."""
    engine = chess.engine.SimpleEngine.popen_uci(find_stockfish())
    if elo:
        engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
        return engine, f"Elo {elo}"
    engine.configure({"Skill Level": level})
    return engine, f"skill level {level}/20"


# --- text views of a position -----------------------------------------------

def move_list(board):
    """Return the game so far as numbered SAN text, from the game's start position."""
    replay = board.root()
    parts = []
    for i, move in enumerate(board.move_stack):
        if replay.turn == chess.WHITE:
            parts.append(f"{replay.fullmove_number}.")
        elif i == 0:
            parts.append(f"{replay.fullmove_number}...")
        parts.append(replay.san(move))
        replay.push(move)
    return " ".join(parts) or "(no moves yet)"


def move_number(board):
    """Move number prefix for the side to move, e.g. '12.' or '12...'."""
    return f"{board.fullmove_number}{'.' if board.turn == chess.WHITE else '...'}"


def piece_list(board):
    lines = []
    for color, name in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
        pieces = []
        for piece_type in PIECE_ORDER:
            letter = chess.piece_symbol(piece_type).upper() if piece_type != chess.PAWN else ""
            for sq in board.pieces(piece_type, color):
                pieces.append(letter + chess.square_name(sq))
        lines.append(f"{name}: {' '.join(pieces)}")
    return "\n".join(lines)


def material(board, color):
    return sum(len(board.pieces(pt, color)) * v for pt, v in PIECE_VALUES.items())


def status_text(board, player, opponent="Stockfish"):
    """Return a short summary of the game state."""
    side = "You" if board.turn == player else opponent
    last = "-"
    if board.move_stack:
        prev = board.copy()
        move = prev.pop()
        last = prev.san(move)
    mine, theirs = material(board, player), material(board, not player)
    diff = mine - theirs
    balance = "equal" if diff == 0 else f"you are {'+' if diff > 0 else ''}{diff}"
    lines = [
        f"Move {board.fullmove_number}, {side} to move. Last move: {last}",
        f"Material: you {mine}, {opponent} {theirs} ({balance})",
    ]
    if board.is_check():
        lines.append("You are in check!" if board.turn == player else f"{opponent} is in check.")
    return "\n".join(lines)


def board_text(board, player):
    return board.unicode(invert_color=True, orientation=player, empty_square="·")


# --- terminal ---------------------------------------------------------------

def flash(text, seconds, erase_above=0, after="(hidden)"):
    """Show text for a few seconds, then erase it and `erase_above` lines before it."""
    print(text)
    if not sys.stdout.isatty():
        return
    try:
        for left in range(int(seconds), 0, -1):
            print(f"(hiding in {left}s)", end="\r", flush=True)
            time.sleep(1)
        time.sleep(seconds - int(seconds))
    except KeyboardInterrupt:
        pass
    # Move the cursor up over the text (and earlier lines), then clear to the end of the screen.
    print(f"\033[{text.count(chr(10)) + 1 + erase_above}F\033[J", end="", flush=True)
    if after:
        print(after)


def sneak_peek(board, player, seconds, opponent="Stockfish"):
    """Show status and board briefly, then erase them and the 'peek' command line."""
    flash(status_text(board, player, opponent) + "\n" + board_text(board, player), seconds,
          erase_above=1, after="(peeked)")


def ask(prompt):
    """input() that returns None on Ctrl+C / Ctrl+D."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None


def parse_peek(cmd, default=3.0):
    """Return the seconds for a 'peek [s]' command, or None if the argument is invalid."""
    parts = cmd.split()
    try:
        return float(parts[1]) if len(parts) > 1 else default
    except ValueError:
        print("Usage: peek [seconds]")
        return None


def parse_move(board, text):
    try:
        return board.parse_san(text)
    except ValueError:
        pass
    try:
        move = chess.Move.from_uci(text.lower())
        if move in board.legal_moves:
            return move
    except ValueError:
        pass
    return None


# --- playing a game ---------------------------------------------------------

def game_result(board, player):
    """Return 'win', 'loss', 'draw' or None while the game goes on."""
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    if outcome.winner is None:
        return "draw"
    return "win" if outcome.winner == player else "loss"


def game_over_message(board, player, opponent="Stockfish"):
    outcome = board.outcome(claim_draw=True)
    if outcome.winner is None:
        return f"Draw ({outcome.termination.name.replace('_', ' ').lower()})."
    return "Checkmate - you win!" if outcome.winner == player else f"Checkmate - {opponent} wins."


def play_game(board, player, engine, think=0.3, opponent="Stockfish", max_moves=None):
    """Play blindfold from `board` until the game ends (or after `max_moves` of your moves).

    Returns (result, peeks) with result 'win', 'loss', 'draw', 'resign', 'quit' or 'limit'.
    """
    peeks = 0
    start = len(board.move_stack)
    while True:
        result = game_result(board, player)
        if result:
            print(game_over_message(board, player, opponent))
            print(move_list(board))
            return result, peeks
        if max_moves and board.turn == player and len(board.move_stack) - start >= 2 * max_moves:
            print(f"{max_moves} moves played.")
            print(move_list(board))
            return "limit", peeks

        if board.turn != player:
            reply = engine.play(board, chess.engine.Limit(time=think))
            prefix = move_number(board)
            san = board.san(reply.move)
            board.push(reply.move)
            print(f"{opponent}: {prefix} {san}")
            continue

        text = ask(f"{move_number(board)} You: ")
        if text is None:
            return "quit", peeks
        cmd = text.lower()
        if not text:
            continue
        if cmd in ("quit", "exit", "q"):
            return "quit", peeks
        if cmd == "help":
            print(GAME_HELP)
        elif cmd == "moves":
            print(move_list(board))
        elif cmd.split()[0] == "peek":
            seconds = parse_peek(cmd)
            if seconds is not None:
                peeks += 1
                sneak_peek(board, player, seconds, opponent)
        elif cmd == "board":
            peeks += 1
            print(status_text(board, player, opponent))
            print(board_text(board, player))
        elif cmd == "pieces":
            print(piece_list(board))
        elif cmd == "legal":
            print(" ".join(sorted(board.san(m) for m in board.legal_moves)))
        elif cmd == "fen":
            print(board.fen())
        elif cmd == "undo":
            if len(board.move_stack) >= 2:
                board.pop()
                board.pop()
                print("Took back the last move pair. " + move_list(board))
            else:
                print("Nothing to undo.")
        elif cmd == "resign":
            print("You resigned.")
            print(move_list(board))
            return "resign", peeks
        else:
            move = parse_move(board, text)
            if move is None:
                print("Illegal or unrecognised move. Try again (or 'legal').")
                continue
            board.push(move)


# --- stats ------------------------------------------------------------------

def load_stats():
    try:
        return json.loads(STATS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_stats(stats):
    DATA.mkdir(exist_ok=True)
    STATS_FILE.write_text(json.dumps(stats, indent=1), encoding="utf-8")


def log_session(mode, **fields):
    """Append one finished session to the stats file."""
    stats = load_stats()
    entry = {"date": time.strftime("%Y-%m-%d %H:%M")}
    entry.update(fields)
    stats.setdefault(mode, {}).setdefault("sessions", []).append(entry)
    save_stats(stats)
