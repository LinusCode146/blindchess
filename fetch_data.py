#!/usr/bin/env python3
"""Download the training data into data/.

- data/puzzles.csv: a sample of popular puzzles from the Lichess puzzle database (CC0)
- data/openings.tsv: named opening lines from lichess-org/chess-openings (CC0)

Needs curl and zstd (brew install zstd). The full puzzle file is ~250 MB compressed;
it is streamed and sampled, so only the sample is written to disk.
"""
import argparse
import csv
import random
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
PUZZLE_URL = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
OPENING_URL = "https://raw.githubusercontent.com/lichess-org/chess-openings/master/{}.tsv"


def fetch_openings():
    rows = []
    for part in "abcde":
        with urllib.request.urlopen(OPENING_URL.format(part)) as resp:
            lines = resp.read().decode("utf-8").splitlines()
        rows.extend(lines[1:])  # skip header
    out = DATA / "openings.tsv"
    out.write_text("eco\tname\tpgn\n" + "\n".join(rows) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} opening lines to {out}")


def fetch_puzzles(sample_size, min_plays, min_popularity):
    for tool in ("curl", "zstd"):
        if not shutil.which(tool):
            sys.exit(f"{tool} not found. Install it with: brew install {tool}")
    curl = subprocess.Popen(["curl", "-fsSL", PUZZLE_URL], stdout=subprocess.PIPE)
    zstd = subprocess.Popen(["zstd", "-dc"], stdin=curl.stdout, stdout=subprocess.PIPE, text=True)
    curl.stdout.close()

    rng = random.Random(146)
    sample = []
    seen = 0
    reader = csv.DictReader(zstd.stdout)
    for i, row in enumerate(reader):
        if i and i % 500000 == 0:
            print(f"  scanned {i:,} puzzles...", flush=True)
        if int(row["NbPlays"]) < min_plays or int(row["Popularity"]) < min_popularity:
            continue
        item = [row["PuzzleId"], row["FEN"], row["Moves"], row["Rating"], row["Themes"]]
        seen += 1
        if len(sample) < sample_size:
            sample.append(item)
        else:
            j = rng.randrange(seen)
            if j < sample_size:
                sample[j] = item
    zstd.wait()
    if curl.wait() != 0:
        sys.exit("Download failed.")

    out = DATA / "puzzles.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["PuzzleId", "FEN", "Moves", "Rating", "Themes"])
        writer.writerows(sample)
    print(f"Wrote {len(sample)} puzzles (from {seen:,} eligible) to {out}")


def main():
    parser = argparse.ArgumentParser(description="Download puzzle and opening data")
    parser.add_argument("--puzzles", type=int, default=50000, help="number of puzzles to keep (default 50000)")
    parser.add_argument("--min-plays", type=int, default=500, help="skip puzzles played fewer times")
    parser.add_argument("--min-popularity", type=int, default=80, help="skip puzzles rated lower (-100..100)")
    parser.add_argument("--skip-puzzles", action="store_true", help="only fetch openings")
    args = parser.parse_args()

    DATA.mkdir(exist_ok=True)
    fetch_openings()
    if not args.skip_puzzles:
        print("Streaming the Lichess puzzle database (~250 MB), this takes a few minutes...")
        fetch_puzzles(args.puzzles, args.min_plays, args.min_popularity)


if __name__ == "__main__":
    main()
