#!/usr/bin/env python3
"""Blindfold chess against Stockfish in the terminal.

Type moves in standard algebraic notation (e4, Nf3, exd5, O-O, e8=Q).
The board is hidden unless you ask for it.
"""
import argparse
import shutil
import sys
import time

import chess
import chess.engine

HELP = """Commands:
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


def find_stockfish():
    path = shutil.which("stockfish")
    if not path:
        sys.exit("Stockfish not found. Install it with: brew install stockfish")
    return path


def configure(engine, args):
    if args.elo:
        engine.configure({"UCI_LimitStrength": True, "UCI_Elo": args.elo})
        return f"Elo {args.elo}"
    engine.configure({"Skill Level": args.level})
    return f"skill level {args.level}/20"


def move_list(board):
    """Return the game so far as numbered SAN text."""
    replay = chess.Board()
    parts = []
    for move in board.move_stack:
        if replay.turn == chess.WHITE:
            parts.append(f"{replay.fullmove_number}.")
        parts.append(replay.san(move))
        replay.push(move)
    return " ".join(parts) or "(no moves yet)"


def piece_list(board):
    lines = []
    for color, name in ((chess.WHITE, "White"), (chess.BLACK, "Black")):
        pieces = []
        for piece_type in (chess.KING, chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN):
            letter = chess.piece_symbol(piece_type).upper() if piece_type != chess.PAWN else ""
            for sq in board.pieces(piece_type, color):
                pieces.append(letter + chess.square_name(sq))
        lines.append(f"{name}: {' '.join(pieces)}")
    return "\n".join(lines)


PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def material(board, color):
    return sum(len(board.pieces(pt, color)) * v for pt, v in PIECE_VALUES.items())


def status_text(board, player):
    """Return a short summary of the game state."""
    side = "You" if board.turn == player else "Stockfish"
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
        f"Material: you {mine}, Stockfish {theirs} ({balance})",
    ]
    if board.is_check():
        lines.append("You are in check!" if board.turn == player else "Stockfish is in check.")
    return "\n".join(lines)


def board_text(board, player):
    return board.unicode(invert_color=True, orientation=player, empty_square="·")


def sneak_peek(board, player, seconds):
    """Show status and board briefly, then erase them from the terminal."""
    text = status_text(board, player) + "\n" + board_text(board, player)
    if not sys.stdout.isatty():
        print(text)
        return
    print(text)
    try:
        for left in range(int(seconds), 0, -1):
            print(f"(hiding in {left}s)", end="\r", flush=True)
            time.sleep(1)
        time.sleep(seconds - int(seconds))
    except KeyboardInterrupt:
        pass
    # Move the cursor up over the peek output and the 'peek' command line, then clear.
    print(f"\033[{text.count(chr(10)) + 2}F\033[J", end="", flush=True)
    print("(peeked)")


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


def game_over_message(board, player):
    outcome = board.outcome(claim_draw=True)
    if outcome is None:
        return None
    if outcome.winner is None:
        return f"Draw ({outcome.termination.name.replace('_', ' ').lower()})."
    return "Checkmate - you win!" if outcome.winner == player else "Checkmate - Stockfish wins."


def main():
    parser = argparse.ArgumentParser(description="Blindfold chess against Stockfish")
    parser.add_argument("-l", "--level", type=int, default=3, choices=range(0, 21), metavar="0-20",
                        help="Stockfish skill level (default 3)")
    parser.add_argument("-e", "--elo", type=int, help="limit strength to an Elo (1320-3190) instead of --level")
    parser.add_argument("-c", "--color", choices=["white", "black", "random"], default="white")
    parser.add_argument("-t", "--think", type=float, default=0.3, help="engine seconds per move (default 0.3)")
    args = parser.parse_args()

    if args.color == "random":
        import random
        args.color = random.choice(["white", "black"])
    player = chess.WHITE if args.color == "white" else chess.BLACK

    board = chess.Board()
    peeks = 0
    engine = chess.engine.SimpleEngine.popen_uci(find_stockfish())
    try:
        strength = configure(engine, args)
        print(f"Blindfold chess vs Stockfish ({strength}). You play {args.color}. Type 'help' for commands.\n")

        while True:
            msg = game_over_message(board, player)
            if msg:
                print(msg)
                print(move_list(board))
                break

            if board.turn != player:
                result = engine.play(board, chess.engine.Limit(time=args.think))
                san = board.san(result.move)
                board.push(result.move)
                num = board.fullmove_number - (1 if board.turn == chess.WHITE else 0)
                print(f"Stockfish: {num}.{'..' if board.turn == chess.WHITE else ''} {san}")
                continue

            prompt = f"{board.fullmove_number}.{'..' if player == chess.BLACK else ''} You: "
            try:
                text = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            cmd = text.lower()

            if not text:
                continue
            if cmd in ("quit", "exit", "q"):
                break
            if cmd == "help":
                print(HELP)
            elif cmd == "moves":
                print(move_list(board))
            elif cmd.split()[0] == "peek":
                parts = cmd.split()
                try:
                    seconds = float(parts[1]) if len(parts) > 1 else 3.0
                except ValueError:
                    print("Usage: peek [seconds]")
                    continue
                peeks += 1
                sneak_peek(board, player, seconds)
            elif cmd == "board":
                peeks += 1
                print(status_text(board, player))
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
                break
            else:
                move = parse_move(board, text)
                if move is None:
                    print("Illegal or unrecognised move. Try again (or 'legal').")
                    continue
                board.push(move)
    finally:
        engine.quit()
        if board.move_stack:
            print(f"Peeks used: {peeks}")


if __name__ == "__main__":
    main()
