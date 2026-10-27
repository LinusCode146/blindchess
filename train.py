#!/usr/bin/env python3
"""Blindfold chess drills.

  python3 train.py tactics    solve Lichess puzzles after seeing the board briefly
  python3 train.py memory     memorise a position, then type every piece's square
  python3 train.py vision     quick questions about squares, diagonals and piece moves
  python3 train.py endgame    convert (or hold) endgames against full-strength Stockfish
  python3 train.py opening    play opening lines from memory against the opening book
  python3 train.py stats      show your progress

Run `python3 train.py <mode> -h` for the options of each mode.
"""
import argparse
import csv
import random
import re
import sys
import time
from collections import defaultdict, deque

import chess
import chess.engine

from common import (DATA, board_text, flash, load_stats, log_session, move_list, move_number,
                    open_engine, parse_move, parse_peek, piece_list, play_game, save_stats,
                    sneak_peek, ask)

COLOR_NAME = {chess.WHITE: "White", chess.BLACK: "Black"}


def require(path, what):
    if not path.exists():
        sys.exit(f"{path.name} not found. Download the {what} first with: python3 fetch_data.py")


def side(value):
    if value == "random":
        return random.choice([chess.WHITE, chess.BLACK])
    return chess.WHITE if value == "white" else chess.BLACK


def show_position(board, player, seconds):
    """Show the board for `seconds` and hide it; with 0 seconds give the pieces as text only."""
    if seconds > 0:
        flash(board_text(board, player), seconds, after="(board hidden)")
    else:
        print(piece_list(board))


def line_san(board, uci_moves):
    """SAN text of a sequence of UCI moves played from `board`."""
    b = board.copy()
    parts = []
    for uci in uci_moves:
        move = chess.Move.from_uci(uci)
        if b.turn == chess.WHITE or not parts:
            parts.append(move_number(b))
        parts.append(b.san(move))
        b.push(move)
    return " ".join(parts)


# --- tactics ----------------------------------------------------------------

TACTICS_HELP = """Commands:
  <move>     your move in SAN (Nxf7+, Qh5, O-O) or UCI
  peek [s]   show the board again for s seconds (puzzle then counts as helped)
  pieces     list all pieces as text (counts as helped)
  hint       which piece to move (counts as helped)
  solution   show the solution (counts as failed)
  skip       next puzzle (counts as failed)
  quit       stop training"""


def load_puzzles():
    path = DATA / "puzzles.csv"
    require(path, "puzzles")
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick_puzzle(pool, rating, done):
    window = 100
    while window < 3000:
        near = [p for p in pool if p["PuzzleId"] not in done and abs(int(p["Rating"]) - rating) <= window]
        if near:
            return random.choice(near)
        window *= 2
    return None


def run_puzzle(p, show):
    """Play one puzzle. Returns 'solved', 'helped', 'failed' or 'quit'."""
    board = chess.Board(p["FEN"])
    moves = p["Moves"].split()
    first = chess.Move.from_uci(moves[0])
    prefix, san = move_number(board), board.san(first)
    board.push(first)
    player = board.turn

    print(f"\nPuzzle {p['PuzzleId']} (rating {p['Rating']}). You are {COLOR_NAME[player]}. "
          f"{COLOR_NAME[not player]} just played {prefix} {san}.")
    show_position(board, player, show)

    helped = False
    i = 1
    while i < len(moves):
        text = ask(f"{move_number(board)} Your move: ")
        if text is None:
            return "quit"
        cmd = text.lower()
        if not text:
            continue
        if cmd in ("quit", "exit", "q"):
            return "quit"
        if cmd == "help":
            print(TACTICS_HELP)
            continue
        if cmd.split()[0] == "peek":
            seconds = parse_peek(cmd)
            if seconds is not None:
                helped = True
                sneak_peek(board, player, seconds, COLOR_NAME[not player])
            continue
        if cmd == "pieces":
            helped = True
            print(piece_list(board))
            continue
        if cmd == "hint":
            helped = True
            sq = chess.Move.from_uci(moves[i]).from_square
            print(f"Move your {chess.piece_name(board.piece_type_at(sq))} on {chess.square_name(sq)}.")
            continue
        if cmd in ("solution", "skip"):
            print(f"Solution: {line_san(board, moves[i:])}")
            return "failed"

        move = parse_move(board, text)
        if move is None:
            print("Illegal or unrecognised move. Try again.")
            continue
        expected = chess.Move.from_uci(moves[i])
        board.push(move)
        if move != expected and not board.is_checkmate():
            board.pop()
            print(f"Wrong. Solution: {line_san(board, moves[i:])}")
            return "failed"
        if board.is_checkmate() or i + 1 >= len(moves):
            break
        reply = chess.Move.from_uci(moves[i + 1])
        prefix, san = move_number(board), board.san(reply)
        board.push(reply)
        print(f"Correct! {COLOR_NAME[not player]}: {prefix} {san}")
        i += 2

    print("Solved!" + (" (with help)" if helped else ""))
    return "helped" if helped else "solved"


def tactics(args):
    puzzles = load_puzzles()
    stats = load_stats()
    t = stats.setdefault("tactics", {})
    rating = args.rating or t.get("rating", 1200)
    solved = set(t.get("solved", []))
    missed = t.setdefault("missed", [])

    pool = puzzles
    if args.theme:
        pool = [p for p in pool if args.theme.lower() in p["Themes"].lower().split()]
        if not pool:
            sys.exit(f"No puzzles with theme '{args.theme}'. Examples: fork pin skewer mateIn2 "
                     "mateIn3 discoveredAttack sacrifice endgame hangingPiece")
    if args.retry_missed:
        pool = [p for p in pool if p["PuzzleId"] in set(missed)]
        if not pool:
            sys.exit("No missed puzzles to retry.")

    print(f"Tactics training. Your puzzle rating: {rating}. Board shown for {args.show:g}s. "
          "Type 'help' for commands.")
    results = defaultdict(int)
    done = set() if args.retry_missed else set(solved)
    for _ in range(args.count):
        p = pick_puzzle(pool, rating, done)
        if p is None:
            print("No more puzzles in this selection.")
            break
        done.add(p["PuzzleId"])
        result = run_puzzle(p, args.show)
        if result == "quit":
            break
        results[result] += 1

        pid, prating = p["PuzzleId"], int(p["Rating"])
        if result != "helped":
            expected = 1 / (1 + 10 ** ((prating - rating) / 400))
            score = 1 if result == "solved" else 0
            change = round(32 * (score - expected))
            rating += change
            print(f"Rating: {rating} ({'+' if change >= 0 else ''}{change})")
        if result == "solved":
            solved.add(pid)
            if pid in missed:
                missed.remove(pid)
        elif pid not in missed:
            missed.append(pid)

        t.update(rating=rating, solved=sorted(solved), missed=missed)
        save_stats(stats)

    total = sum(results.values())
    if total:
        print(f"\n{total} puzzles: {results['solved']} solved, {results['helped']} with help, "
              f"{results['failed']} failed. Rating: {rating}")
        log_session("tactics", puzzles=total, solved=results["solved"], helped=results["helped"],
                    failed=results["failed"], rating=rating)


# --- position memory --------------------------------------------------------

TOKEN = re.compile(r"^([KQRBNP]?)([a-h][1-8])$")


def parse_pieces(text, color):
    """Parse 'Ke1 Qd1 e4 Pf2' into a set of (piece_type, color, square). Returns (set, bad tokens)."""
    found, bad = set(), []
    for token in re.split(r"[\s,]+", text.strip()):
        if not token:
            continue
        m = TOKEN.match(token[0].upper() + token[1:] if token[0] in "kqrnp" else token)
        if not m:
            bad.append(token)
            continue
        letter = m.group(1) or "P"
        found.add((chess.Piece.from_symbol(letter).piece_type, color, chess.parse_square(m.group(2))))
    return found, bad


def describe(items):
    def key(item):
        return (PIECE_RANK[item[0]], item[2])
    out = []
    for pt, _, sq in sorted(items, key=key):
        out.append(("" if pt == chess.PAWN else chess.piece_symbol(pt).upper()) + chess.square_name(sq))
    return " ".join(out) or "-"


PIECE_RANK = {chess.KING: 0, chess.QUEEN: 1, chess.ROOK: 2, chess.BISHOP: 3, chess.KNIGHT: 4, chess.PAWN: 5}


def memory(args):
    require(DATA / "puzzles.csv", "puzzles")
    positions = [p["FEN"] for p in load_puzzles()
                 if args.min_pieces <= len(chess.Board(p["FEN"]).piece_map()) <= args.max_pieces]
    if not positions:
        sys.exit("No positions with that many pieces.")

    print(f"Position memory. Look at the board for {args.show:g}s, then type each side's pieces.\n"
          "Format: Ke1 Qd1 Rf1 Nc3 e4 f2 (pieces in capitals, pawns as just the square).")
    scores = []
    for n in range(1, args.count + 1):
        board = chess.Board(random.choice(positions))
        actual = {(pc.piece_type, pc.color, sq) for sq, pc in board.piece_map().items()}
        print(f"\nPosition {n}/{args.count}: {len(actual)} pieces.")
        flash(board_text(board, chess.WHITE), args.show, after="(board hidden)")

        guess = set()
        stop = False
        for color in (chess.WHITE, chess.BLACK):
            while True:
                text = ask(f"{COLOR_NAME[color]} pieces: ")
                if text is None or text.lower() in ("quit", "q"):
                    stop = True
                    break
                found, bad = parse_pieces(text, color)
                if bad:
                    print(f"Could not read: {' '.join(bad)}. Type that side again.")
                    continue
                guess |= found
                break
            if stop:
                break
        if stop:
            break

        right = actual & guess
        missing = actual - guess
        wrong = guess - actual
        score = len(right) / (len(actual) + len(wrong))
        scores.append(score)
        print(f"{len(right)}/{len(actual)} correct, {len(wrong)} wrong -> {score:.0%}")
        for color in (chess.WHITE, chess.BLACK):
            miss = [i for i in missing if i[1] == color]
            extra = [i for i in wrong if i[1] == color]
            if miss or extra:
                print(f"  {COLOR_NAME[color]}: missed {describe(miss)}; wrong {describe(extra)}")
        print(board_text(board, chess.WHITE))

    if scores:
        avg = sum(scores) / len(scores)
        print(f"\nAverage score: {avg:.0%} over {len(scores)} positions.")
        log_session("memory", positions=len(scores), average=round(avg, 3), show=args.show,
                    max_pieces=args.max_pieces)


# --- board vision -----------------------------------------------------------

def rand_square():
    return random.choice(chess.SQUARES)


def sq_name(sq):
    return chess.square_name(sq)


def knight_distance(a, b):
    seen = {a: 0}
    queue = deque([a])
    while queue:
        sq = queue.popleft()
        if sq == b:
            return seen[sq]
        for nxt in chess.SquareSet(chess.BB_KNIGHT_ATTACKS[sq]):
            if nxt not in seen:
                seen[nxt] = seen[sq] + 1
                queue.append(nxt)
    return None


def empty_attacks(piece_type, sq):
    board = chess.BaseBoard(None)
    board.set_piece_at(sq, chess.Piece(piece_type, chess.WHITE))
    return board.attacks(sq)


def is_light(sq):
    return (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1


def q_color():
    sq = rand_square()
    answer = "light" if is_light(sq) else "dark"
    return f"Colour of {sq_name(sq)}? (light/dark)", lambda a: a[:1] == answer[0], answer


def q_knight_distance():
    a, b = rand_square(), rand_square()
    while a == b:
        b = rand_square()
    d = knight_distance(a, b)
    return f"Knight from {sq_name(a)} to {sq_name(b)}: fewest moves?", lambda x: x == str(d), str(d)


def q_knight_squares():
    sq = rand_square()
    targets = {sq_name(s) for s in chess.SquareSet(chess.BB_KNIGHT_ATTACKS[sq])}
    answer = " ".join(sorted(targets))
    return (f"All squares a knight on {sq_name(sq)} attacks?",
            lambda x: set(re.split(r"[\s,]+", x)) - {""} == targets, answer)


def q_reach():
    pt = random.choice([chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.KING])
    sq = rand_square()
    attacks = empty_attacks(pt, sq)
    if random.random() < 0.5 and attacks:
        target = random.choice(list(attacks))
    else:
        target = random.choice([s for s in chess.SQUARES if s != sq])
    answer = "yes" if target in attacks else "no"
    return (f"Can a {chess.piece_name(pt)} on {sq_name(sq)} reach {sq_name(target)} in one move "
            "(empty board)? (y/n)", lambda x: x[:1] == answer[0], answer)


def q_diagonal():
    a = rand_square()
    diag = [s for s in empty_attacks(chess.BISHOP, a)]
    b = random.choice(diag) if random.random() < 0.5 else random.choice([s for s in chess.SQUARES if s != a])
    answer = "yes" if b in diag else "no"
    return (f"Are {sq_name(a)} and {sq_name(b)} on the same diagonal? (y/n)",
            lambda x: x[:1] == answer[0], answer)


def q_bishop_distance():
    a = rand_square()
    b = rand_square()
    while a == b:
        b = rand_square()
    if is_light(a) != is_light(b):
        answer = "x"
    elif b in empty_attacks(chess.BISHOP, a):
        answer = "1"
    else:
        answer = "2"
    return (f"Bishop from {sq_name(a)} to {sq_name(b)}: fewest moves? (x if impossible)",
            lambda x: x == answer, answer)


VISION_TYPES = {
    "color": q_color,
    "knight": q_knight_distance,
    "knightsquares": q_knight_squares,
    "reach": q_reach,
    "diagonal": q_diagonal,
    "bishop": q_bishop_distance,
}


def vision(args):
    types = args.types.split(",") if args.types else list(VISION_TYPES)
    unknown = [t for t in types if t not in VISION_TYPES]
    if unknown:
        sys.exit(f"Unknown question type(s): {', '.join(unknown)}. Choose from: {', '.join(VISION_TYPES)}")

    print(f"Board vision: {args.count} questions. Answer as fast as you can ('quit' to stop).\n")
    right, asked = 0, 0
    start = time.monotonic()
    for n in range(1, args.count + 1):
        question, check, answer = VISION_TYPES[random.choice(types)]()
        t0 = time.monotonic()
        reply = ask(f"{n}. {question} ")
        if reply is None or reply.lower() in ("quit", "q"):
            break
        asked += 1
        took = time.monotonic() - t0
        if check(reply.lower()):
            right += 1
            print(f"   Correct ({took:.1f}s)")
        else:
            print(f"   Wrong - {answer} ({took:.1f}s)")

    if asked:
        total = time.monotonic() - start
        print(f"\n{right}/{asked} correct, {total / asked:.1f}s per question.")
        log_session("vision", questions=asked, correct=right, seconds_per_question=round(total / asked, 1))


# --- endgames ---------------------------------------------------------------

# key: (description, goal, pieces for the attacker, fixed FEN or None, player color for fixed FENs)
ENDGAMES = {
    "kqk": ("King and queen vs king", "win", "Q", None),
    "krk": ("King and rook vs king", "win", "R", None),
    "kbbk": ("King and two bishops vs king", "win", "BB", None),
    "kbnk": ("King, bishop and knight vs king", "win", "BN", None),
    "kqkr": ("Queen vs rook", "win", "Q/r", None),
    "kpk": ("King and pawn vs king (key squares)", "win", None, "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1"),
    "lucena": ("Lucena position (build the bridge)", "win", None, "1K1k4/1P6/8/8/8/8/r7/2R5 w - - 0 1"),
    "philidor": ("Philidor position (defend as Black)", "draw", None, "3k4/8/7r/3PK3/8/8/8/R7 b - - 0 1"),
}


def random_endgame(pieces, player, engine):
    """Random legal position where `player` has king + pieces and is clearly winning."""
    own, _, theirs = pieces.partition("/")
    for _ in range(500):
        board = chess.Board(None)
        board.turn = player
        squares = random.sample(chess.SQUARES, 2 + len(own) + len(theirs))
        board.set_piece_at(squares[0], chess.Piece(chess.KING, player))
        board.set_piece_at(squares[1], chess.Piece(chess.KING, not player))
        for sq, letter in zip(squares[2:], own.upper() + theirs.upper()):
            color = player if squares.index(sq) - 2 < len(own) else not player
            pt = chess.Piece.from_symbol(letter).piece_type
            if pt == chess.PAWN and chess.square_rank(sq) in (0, 7):
                break
            board.set_piece_at(sq, chess.Piece(pt, color))
        else:
            if own.upper() == "BB":
                bishops = list(board.pieces(chess.BISHOP, player))
                if is_light(bishops[0]) == is_light(bishops[1]):
                    continue
            if not board.is_valid() or board.is_game_over():
                continue
            score = engine.analyse(board, chess.engine.Limit(depth=14))["score"].pov(player)
            # Clearly winning, but not a trivial mate in a few moves.
            if score.is_mate() and score.mate() > 5 or (score.score() or 0) >= 500:
                return board
    sys.exit("Could not generate a position, please try again.")


def endgame(args):
    if args.list:
        for key, (desc, goal, _, _) in ENDGAMES.items():
            print(f"  {key:9} {desc} - goal: {goal}")
        return
    key = args.name or random.choice(list(ENDGAMES))
    if key not in ENDGAMES:
        sys.exit(f"Unknown endgame '{key}'. Use --list to see all.")
    desc, goal, pieces, fen = ENDGAMES[key]

    engine, _ = open_engine(20)
    try:
        if fen:
            board = chess.Board(fen)
            player = board.turn
        else:
            player = side(args.color)
            board = random_endgame(pieces, player, engine)

        if goal == "win":
            target = "Goal: win (checkmate, mind the 50-move rule)."
        else:
            target = f"Goal: hold the draw for {args.hold} moves."
        print(f"Endgame: {desc}. You play {COLOR_NAME[player]}. {target}")
        print(piece_list(board))
        if args.show > 0:
            flash(board_text(board, player), args.show, after="(board hidden)")
        print("Type 'help' for commands.\n")

        result, peeks = play_game(board, player, engine, args.think,
                                  max_moves=args.hold if goal == "draw" else None)
    finally:
        engine.quit()

    success = result == "win" if goal == "win" else result in ("draw", "limit")
    if result != "quit":
        print("Well done!" if success else "Not this time.", f"Peeks used: {peeks}")
        log_session("endgame", endgame=key, result=result, success=success, peeks=peeks)


# --- openings ---------------------------------------------------------------

def load_openings():
    path = DATA / "openings.tsv"
    require(path, "openings")
    lines = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            moves = [t for t in row["pgn"].split() if not re.match(r"^\d+\.", t)]
            lines.append((row["eco"], row["name"], moves))
    return lines


def opening(args):
    lines = load_openings()
    if args.list is not None:
        families = defaultdict(int)
        for _, name, _ in lines:
            if args.list.lower() in name.lower():
                families[name.split(":")[0]] += 1
        for name, count in sorted(families.items()):
            print(f"  {name} ({count} lines)")
        return

    chosen = [l for l in lines
              if (not args.name or args.name.lower() in l[1].lower()) and (not args.eco or l[0].startswith(args.eco.upper()))]
    if not chosen:
        sys.exit("No opening lines match. Try: python3 train.py opening --list sicilian")

    # Tree of book moves: prefix -> {next SAN: number of lines through it}, and names of exact lines.
    tree = defaultdict(lambda: defaultdict(int))
    names = {}
    for eco, name, moves in chosen:
        for i in range(len(moves)):
            tree[tuple(moves[:i])][moves[i]] += 1
        names[tuple(moves)] = f"{eco} {name}"

    player = side(args.color)
    family = sorted({l[1].split(":")[0] for l in chosen})
    label = args.name or args.eco or "all openings"
    print(f"Opening drill: {label} ({len(chosen)} lines). You play {COLOR_NAME[player]}.")
    if len(family) <= 3:
        print("Covers: " + ", ".join(family))
    print("Play the book moves from memory. Commands: book (show book moves), peek, moves, quit.\n")

    for n in range(1, args.count + 1):
        board = chess.Board()
        history = []
        mistakes = played = 0
        reached = "(not a named line yet)"
        quit_now = False
        while True:
            options = tree.get(tuple(history))
            if not options:
                break
            if board.turn != player:
                moves, weights = zip(*options.items())
                san = random.choices(moves, weights)[0]
                print(f"Book: {move_number(board)} {san}")
                board.push_san(san)
                history.append(san)
                reached = names.get(tuple(history), reached)
                continue
            text = ask(f"{move_number(board)} You: ")
            if text is None or text.lower() in ("quit", "q"):
                quit_now = True
                break
            cmd = text.lower()
            if cmd == "book":
                mistakes += 1
                print("Book moves: " + ", ".join(sorted(options)))
                continue
            if cmd.split()[0] == "peek":
                seconds = parse_peek(cmd)
                if seconds is not None:
                    sneak_peek(board, player, seconds, "Book")
                continue
            if cmd == "moves":
                print(move_list(board))
                continue
            move = parse_move(board, text)
            if move is None:
                print("Illegal or unrecognised move.")
                continue
            san = board.san(move)
            if san not in options:
                mistakes += 1
                print(f"Not in the book. Book moves here: {', '.join(sorted(options))}")
                continue
            played += 1
            board.push(move)
            history.append(san)
            reached = names.get(tuple(history), reached)

        if not quit_now:
            print(f"End of book after {move_list(board)}")
        if played or mistakes:
            print(f"Line: {reached}. {played} moves, {mistakes} mistakes.")
            log_session("opening", line=reached, moves=played, mistakes=mistakes)
        if quit_now:
            break

        if args.continue_game and not board.is_game_over():
            engine, strength = open_engine(args.level)
            try:
                print(f"\nPlaying on against Stockfish ({strength}).")
                play_game(board, player, engine)
            finally:
                engine.quit()
        if n < args.count:
            print(f"\n--- Drill {n + 1}/{args.count} ---")


# --- stats ------------------------------------------------------------------

def show_stats(args):
    stats = load_stats()
    if not stats:
        print("No training recorded yet.")
        return
    t = stats.get("tactics", {})
    if t:
        print(f"Tactics rating: {t.get('rating')}  solved: {len(t.get('solved', []))}  "
              f"to retry: {len(t.get('missed', []))}")
    for mode in ("tactics", "memory", "vision", "endgame", "opening"):
        sessions = stats.get(mode, {}).get("sessions", [])
        if not sessions:
            continue
        print(f"\n{mode} - last {min(5, len(sessions))} of {len(sessions)} sessions:")
        for s in sessions[-5:]:
            print("  " + ", ".join(f"{k}={v}" for k, v in s.items()))


def main():
    parser = argparse.ArgumentParser(description="Blindfold chess drills",
                                     formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    p = sub.add_parser("tactics", help="solve puzzles after seeing the board briefly")
    p.add_argument("-s", "--show", type=float, default=3, help="seconds to show the board; 0 = pieces as text only")
    p.add_argument("-n", "--count", type=int, default=10, help="number of puzzles (default 10)")
    p.add_argument("--theme", help="only this theme, e.g. fork, pin, mateIn2, endgame")
    p.add_argument("--rating", type=int, help="set your puzzle rating (default: saved rating or 1200)")
    p.add_argument("--retry-missed", action="store_true", help="only puzzles you failed before")
    p.set_defaults(func=tactics)

    p = sub.add_parser("memory", help="memorise a position, then type every piece")
    p.add_argument("-s", "--show", type=float, default=5, help="seconds to show the board (default 5)")
    p.add_argument("-n", "--count", type=int, default=5, help="number of positions (default 5)")
    p.add_argument("--min-pieces", type=int, default=4)
    p.add_argument("--max-pieces", type=int, default=10, help="most pieces on the board (default 10)")
    p.set_defaults(func=memory)

    p = sub.add_parser("vision", help="quick questions about squares and piece moves")
    p.add_argument("-n", "--count", type=int, default=20, help="number of questions (default 20)")
    p.add_argument("--types", help=f"comma-separated subset of: {','.join(VISION_TYPES)}")
    p.set_defaults(func=vision)

    p = sub.add_parser("endgame", help="win or hold endgames against full-strength Stockfish")
    p.add_argument("name", nargs="?", help="endgame to play (default: random); see --list")
    p.add_argument("--list", action="store_true", help="list the endgames")
    p.add_argument("-c", "--color", choices=["white", "black", "random"], default="white",
                   help="your side in generated endgames")
    p.add_argument("-s", "--show", type=float, default=5, help="seconds to show the start position; 0 = text only")
    p.add_argument("-t", "--think", type=float, default=0.5, help="engine seconds per move")
    p.add_argument("--hold", type=int, default=30, help="moves to survive in drawing endgames (default 30)")
    p.set_defaults(func=endgame)

    p = sub.add_parser("opening", help="play opening lines from memory")
    p.add_argument("--name", help="opening name filter, e.g. 'Italian Game' or 'Sicilian Defense: Najdorf'")
    p.add_argument("--eco", help="ECO code prefix, e.g. C50 or B9")
    p.add_argument("--list", nargs="?", const="", metavar="FILTER", help="list opening families")
    p.add_argument("-c", "--color", choices=["white", "black", "random"], default="white")
    p.add_argument("-n", "--count", type=int, default=1, help="number of drills (default 1)")
    p.add_argument("--continue", dest="continue_game", action="store_true",
                   help="play on against Stockfish after the book ends")
    p.add_argument("-l", "--level", type=int, default=3, help="Stockfish level for --continue (default 3)")
    p.set_defaults(func=opening)

    p = sub.add_parser("stats", help="show your progress")
    p.set_defaults(func=show_stats)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
