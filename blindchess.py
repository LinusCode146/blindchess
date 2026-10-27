#!/usr/bin/env python3
"""Blindfold chess against Stockfish in the terminal.

Type moves in standard algebraic notation (e4, Nf3, exd5, O-O, e8=Q).
The board is hidden unless you ask for it. For drills (tactics, memory,
board vision, endgames, openings) see train.py.
"""
import argparse
import random

import chess

from common import open_engine, play_game


def main():
    parser = argparse.ArgumentParser(description="Blindfold chess against Stockfish")
    parser.add_argument("-l", "--level", type=int, default=3, choices=range(0, 21), metavar="0-20",
                        help="Stockfish skill level (default 3)")
    parser.add_argument("-e", "--elo", type=int, help="limit strength to an Elo (1320-3190) instead of --level")
    parser.add_argument("-c", "--color", choices=["white", "black", "random"], default="white")
    parser.add_argument("-t", "--think", type=float, default=0.3, help="engine seconds per move (default 0.3)")
    args = parser.parse_args()

    if args.color == "random":
        args.color = random.choice(["white", "black"])
    player = chess.WHITE if args.color == "white" else chess.BLACK

    board = chess.Board()
    engine, strength = open_engine(args.level, args.elo)
    try:
        print(f"Blindfold chess vs Stockfish ({strength}). You play {args.color}. Type 'help' for commands.\n")
        _, peeks = play_game(board, player, engine, args.think)
    finally:
        engine.quit()
    if board.move_stack:
        print(f"Peeks used: {peeks}")


if __name__ == "__main__":
    main()
