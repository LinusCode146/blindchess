#!/usr/bin/env python3
"""Start menu for the blindfold chess tools: pick a game or drill and its options."""
import subprocess
import sys
from pathlib import Path

import blindchess
import train
from common import DATA, ask

HERE = Path(__file__).resolve().parent


class Back(Exception):
    """Raised when the user leaves a sub-menu."""


def option(label, default="", choices=None):
    """Ask for one setting. Enter keeps the default; 'b' or Ctrl+D goes back to the menu."""
    hint = f" [{default}]" if default != "" else ""
    while True:
        text = ask(f"  {label}{hint}: ")
        if text is None or text.lower() in ("b", "back"):
            raise Back
        text = text or str(default)
        if not choices or text.lower() in choices:
            return text
        print(f"  Choose one of: {', '.join(choices)}")


def number(label, default, low, high, cast=int):
    while True:
        text = option(label, default)
        try:
            value = cast(text)
            if low <= value <= high:
                return value
        except ValueError:
            pass
        print(f"  Enter a number from {low} to {high}.")


COLORS = ("white", "black", "random")


def play_menu():
    color = option("Your colour (white/black/random)", "white", COLORS)
    strength = number("Strength: level 0-20, or an Elo 1320-3190", 3, 0, 3190)
    if 20 < strength < 1320:
        print("  That is neither a level (0-20) nor a valid Elo; using level 3.")
        strength = 3
    argv = ["-c", color, "-e" if strength > 20 else "-l", str(strength)]
    blindchess.run(blindchess.build_parser().parse_args(argv))


def tactics_menu():
    stats_rating = train.load_stats().get("tactics", {}).get("rating", 1200)
    print(f"  Your puzzle rating: {stats_rating}")
    theme = option("Theme, e.g. fork, pin, skewer, mateIn2, endgame (Enter = any)")
    show = number("Seconds to show the board (0 = pieces as text)", 3, 0, 60, float)
    count = number("Number of puzzles", 10, 1, 500)
    retry = option("Only retry puzzles you missed? (y/n)", "n", ("y", "n", "yes", "no"))
    argv = ["tactics", "-s", str(show), "-n", str(count)]
    if theme:
        argv += ["--theme", theme]
    if retry.startswith("y"):
        argv.append("--retry-missed")
    run_train(argv)


def memory_menu():
    show = number("Seconds to show the board", 5, 1, 120, float)
    pieces = number("Most pieces on the board", 10, 4, 32)
    count = number("Number of positions", 5, 1, 100)
    run_train(["memory", "-s", str(show), "--max-pieces", str(pieces), "--min-pieces", str(min(4, pieces)),
               "-n", str(count)])


def vision_menu():
    print("  Question types: " + ", ".join(train.VISION_TYPES))
    types = option("Types, comma-separated (Enter = all)")
    count = number("Number of questions", 20, 1, 500)
    argv = ["vision", "-n", str(count)]
    if types:
        argv += ["--types", types.replace(" ", "")]
    run_train(argv)


def endgame_menu():
    keys = list(train.ENDGAMES)
    for i, key in enumerate(keys, 1):
        desc, goal = train.ENDGAMES[key][:2]
        print(f"  {i}  {desc} ({goal})")
    pick = option("Endgame number (Enter = random)", "random")
    argv = ["endgame"]
    if pick != "random":
        if not pick.isdigit() or not 1 <= int(pick) <= len(keys):
            print("  Unknown endgame.")
            return
        argv.append(keys[int(pick) - 1])
    if pick == "random" or train.ENDGAMES[argv[-1]][3] is None:
        argv += ["-c", option("Your colour (white/black/random)", "white", COLORS)]
    argv += ["-s", str(number("Seconds to show the start position (0 = text only)", 5, 0, 60, float))]
    run_train(argv)


def opening_menu():
    while True:
        name = option("Opening, e.g. Italian Game, Sicilian Defense: Najdorf, French ('?' to list)")
        if name.startswith("?"):
            run_train(["opening", "--list", name[1:].strip()])
            continue
        if name:
            break
        print("  Type part of an opening name, or '?' to see them all ('?sicilian' to search).")
    color = option("Your colour (white/black/random)", "white", COLORS)
    count = number("Number of drills", 3, 1, 50)
    cont = option("Play on against Stockfish after the book? (y/n)", "n", ("y", "n", "yes", "no"))
    argv = ["opening", "--name", name, "-c", color, "-n", str(count)]
    if cont.startswith("y"):
        argv.append("--continue")
    run_train(argv)


def run_train(argv):
    train_args = train.build_parser().parse_args(argv)
    train_args.func(train_args)


def download_data():
    subprocess.run([sys.executable, str(HERE / "fetch_data.py")], check=False)


def has_data():
    return (DATA / "puzzles.csv").exists() and (DATA / "openings.tsv").exists()


MENU = [
    ("1", "Play a game against Stockfish", play_menu),
    ("2", "Tactics puzzles", tactics_menu),
    ("3", "Position memory", memory_menu),
    ("4", "Board vision quiz", vision_menu),
    ("5", "Endgames", endgame_menu),
    ("6", "Opening drill", opening_menu),
    ("7", "Progress and stats", lambda: run_train(["stats"])),
]


def main():
    print("Blindfold chess")
    while True:
        print()
        for key, label, _ in MENU:
            print(f"  {key}  {label}")
        if not has_data():
            print("  d  Download puzzles and openings (needed for 2, 3 and 6)")
        print("  q  Quit")
        choice = ask("> ")
        if choice is None or choice.lower() in ("q", "quit", "exit"):
            break
        actions = {key: fn for key, _, fn in MENU}
        actions["d"] = download_data
        fn = actions.get(choice.lower())
        if fn is None:
            print("Choose a number from the menu.")
            continue
        if choice in ("1", "2", "3", "4", "5", "6"):
            print("  (Enter keeps the value in brackets, 'b' goes back to the menu)")
        try:
            fn()
        except Back:
            continue
        except SystemExit as e:
            # Drills exit with a message when e.g. data is missing; stay in the menu.
            if e.code not in (None, 0) and not isinstance(e.code, int):
                print(e.code)
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
