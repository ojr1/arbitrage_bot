# scripts/freeze_bot/market_dictionary.py
"""
Builds a market-ID dictionary from an OddsPapi payload. Costs ZERO API requests.

The feed carries no market names, only numeric IDs. But a few bookmakers publish
descriptive bookmakerOutcomeId strings (betsson 'TTSLG-nogoal', sbobet 'NG',
cloudbet 'draw', blaze 'hcp=0:5/...'). Because market IDs are shared across the
whole feed, one book's label names that market for all 154.

Writes data/market_dictionary.csv and prints a goal/score-focused summary.

Usage:
    python scripts/freeze_bot/market_dictionary.py <payload.json>
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "market_dictionary.csv"

# Keywords that make a market worth printing to the console.
FOCUS_WORDS = ("tts", "score", "goal", "ng", "hf", "af", "first", "last", "nogoal")

# Tokens this short or this long are noise rather than labels.
MIN_TOKEN = 2
MAX_TOKEN = 20

# Split IDs on anything that isn't a letter or digit.
SPLITTER = re.compile(r"[^A-Za-z0-9]+")


def load_fixture(path_arg: str) -> dict:
    path = Path(path_arg)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        sys.exit(f"ERROR: file not found: {path}")

    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"Reading {path.name} ({size_mb:.1f} MB)...\n")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and "bookmakerOdds" in item:
                return item
        sys.exit("ERROR: no fixture record with 'bookmakerOdds' in that list.")

    if not isinstance(payload, dict) or "bookmakerOdds" not in payload:
        sys.exit("ERROR: payload has no 'bookmakerOdds' key.")
    return payload


def is_wordy(token: str) -> bool:
    """
    Keep human-written tokens, drop random-looking IDs.

    'home', 'nogoal', 'hcp' -> keep (all lowercase letters)
    'NG', 'HF', 'TTSLG'     -> keep (short all-uppercase)
    'JzwAFyVIK0u'           -> drop (mixed case, contains a digit)
    '4274729907'            -> drop (all digits)
    """
    if not (MIN_TOKEN <= len(token) <= MAX_TOKEN):
        return False
    if not token.isalpha():
        return False
    if token.islower():
        return True
    if token.isupper() and len(token) <= 8:
        return True
    return False


def outcome_sort_key(outcome_id: str):
    try:
        return (0, int(outcome_id))
    except (TypeError, ValueError):
        return (1, str(outcome_id))


def scan(books: dict):
    """Walk every book and market once, gathering labels and ordered prices."""
    market_books = defaultdict(set)            # market_id -> {slugs}
    market_labels = defaultdict(Counter)       # market_id -> Counter of tokens
    market_label_source = {}                   # market_id -> (slug, raw id string)
    market_prices = defaultdict(lambda: defaultdict(list))  # market_id -> pos -> [prices]
    market_outcome_ids = {}                    # market_id -> [outcome ids in order]

    for slug, book_data in books.items():
        markets = (book_data or {}).get("markets", {}) or {}

        for market_id, market_data in markets.items():
            outcomes = (market_data or {}).get("outcomes", {}) or {}
            if not outcomes:
                continue

            ordered = sorted(outcomes.keys(), key=outcome_sort_key)
            market_books[market_id].add(slug)
            market_outcome_ids.setdefault(market_id, ordered)

            for position, outcome_id in enumerate(ordered):
                players = (outcomes[outcome_id] or {}).get("players", {}) or {}
                player = players.get("0", {}) or {}

                raw_id = player.get("bookmakerOutcomeId")
                name = player.get("playerName")
                for source in (raw_id, name):
                    if not isinstance(source, str) or not source.strip():
                        continue
                    tokens = [t for t in SPLITTER.split(source) if is_wordy(t)]
                    if tokens:
                        market_labels[market_id].update(tokens)
                        if market_id not in market_label_source and raw_id:
                            market_label_source[market_id] = (slug, raw_id[:80])

                try:
                    market_prices[market_id][position].append(float(player.get("price")))
                except (TypeError, ValueError):
                    continue

    return market_books, market_labels, market_label_source, market_prices, market_outcome_ids


def build_rows(market_books, market_labels, market_label_source, market_prices, market_outcome_ids):
    rows = []
    for market_id, slugs in market_books.items():
        positions = market_prices[market_id]
        outcome_count = len(market_outcome_ids.get(market_id, []))

        medians = []
        for position in sorted(positions.keys()):
            prices = [p for p in positions[position] if p and p > 1.001]
            medians.append(f"{median(prices):.2f}" if prices else "n/a")

        labels = market_labels[market_id]
        label_text = " ".join(token for token, _ in labels.most_common(10))
        source_slug, source_id = market_label_source.get(market_id, ("", ""))

        rows.append({
            "market_id": market_id,
            "books": len(slugs),
            "outcomes": outcome_count,
            "labels": label_text,
            "median_prices_in_outcome_order": " | ".join(medians),
            "label_source_book": source_slug,
            "label_source_id": source_id,
        })

    rows.sort(key=lambda r: -r["books"])
    return rows


def write_csv(rows: list) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["market_id", "books", "outcomes", "labels",
              "median_prices_in_outcome_order", "label_source_book", "label_source_id"]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def print_focus(rows: list) -> None:
    print("=" * 100)
    print("GOAL / SCORE-RELATED MARKETS (labelled)")
    print("=" * 100)
    print(f"{'Market':<10}{'Books':<7}{'Out':<5}{'Median prices (outcome order)':<38}Labels")
    print("-" * 100)

    shown = 0
    for row in rows:
        labels_lower = row["labels"].lower()
        if not labels_lower:
            continue
        if not any(word in labels_lower.split() for word in FOCUS_WORDS):
            continue
        print(f"{row['market_id']:<10}{row['books']:<7}{row['outcomes']:<5}"
              f"{row['median_prices_in_outcome_order']:<38}{row['labels'][:44]}")
        shown += 1

    if not shown:
        print("None matched — open the CSV and sort by 'books' instead.")
    print()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/freeze_bot/market_dictionary.py <payload.json>")

    fixture = load_fixture(sys.argv[1])
    books = fixture.get("bookmakerOdds", {}) or {}
    print(f"Fixture {fixture.get('fixtureId')} | tournament {fixture.get('tournamentId')} "
          f"| {len(books)} bookmakers\n")

    scanned = scan(books)
    rows = build_rows(*scanned)
    write_csv(rows)

    labelled = sum(1 for r in rows if r["labels"])
    print_focus(rows)

    print("=" * 100)
    print("DICTIONARY COMPLETE")
    print("=" * 100)
    print(f"  Markets found:        {len(rows)}")
    print(f"  Markets with labels:  {labelled} ({labelled / len(rows) * 100:.0f}%)")
    print(f"  Written to:           {OUTPUT_PATH}")
    print("  API requests used:    0")


if __name__ == "__main__":
    main()