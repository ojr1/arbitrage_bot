# scripts/freeze_bot/offline_probe.py
"""
Offline probe for the Freeze bot. Costs ZERO API requests.

Answers two questions from an already-saved OddsPapi payload:
  1. Is Sky Bet present in the bookmaker roster?
  2. Does any bookmaker carry a First Team To Score (FTTS) market?

Handles both payload shapes:
  - a single fixture record (dict with 'bookmakerOdds')
  - a list of fixture records

Usage:
    python scripts/freeze_bot/offline_probe.py
    python scripts/freeze_bot/offline_probe.py path/to/payload.json
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

# Anchor to the project root rather than the working directory, so this runs
# correctly from a subfolder. (Same fix applied in the v2 Betfair client.)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

# Substrings that would appear in a Sky Bet bookmaker slug.
SKY_HINTS = ("sky",)

# Substrings that would appear in a betslip deep-link URL for an FTTS market.
# Deliberately broad — false positives are fine, we read the hits by eye.
FTTS_HINTS = (
    "first-team", "firstteam", "first_team",
    "team-to-score", "teamtoscore", "team_to_score",
    "first-to-score", "firsttoscore",
    "score-first", "scorefirst", "score_first",
    "first-goal", "firstgoal",
    "fts", "ttsf",
)

# A market must appear in at least this many bookmakers to be considered
# "standard" rather than an obscure one-off.
MIN_BOOKS_FOR_CANDIDATE = 15

# A third/longest outcome at or above this price suggests "No Goal"
# rather than a 1X2 draw.
LONG_OUTCOME_FLOOR = 7.0

# Cap how many price shapes we keep per market. Across many fixtures this
# would otherwise grow enormous, and the median barely moves after a few
# thousand samples.
MAX_SHAPES_PER_MARKET = 3000


def find_payload() -> Path:
    """Locate an OddsPapi payload, or exit with a clear message."""
    if len(sys.argv) > 1:
        candidate = Path(sys.argv[1])
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        if not candidate.exists():
            sys.exit(f"ERROR: file not found: {candidate}")
        return candidate

    if not RAW_DIR.exists():
        sys.exit(f"ERROR: no raw data folder at {RAW_DIR}")

    # Largest JSON first — the odds payloads dwarf everything else in there.
    files = sorted(RAW_DIR.glob("*.json"), key=lambda p: p.stat().st_size, reverse=True)
    if not files:
        sys.exit(f"ERROR: no .json files in {RAW_DIR}")

    for path in files:
        # Betfair market dumps also live here — skip anything without the
        # OddsPapi signature key. Peek at the first 4000 chars to stay fast.
        with path.open("r", encoding="utf-8") as handle:
            head = handle.read(4000)
        if "bookmakerOdds" in head:
            return path

    sys.exit(
        f"ERROR: no OddsPapi payload found in {RAW_DIR}\n"
        "       (looked for a JSON file containing 'bookmakerOdds')"
    )


def extract_fixtures(payload) -> list:
    """
    Normalise either payload shape into a flat list of fixture records.

    A fixture record is any dict carrying a 'bookmakerOdds' key.
    """
    fixtures = []

    def walk(node, depth=0):
        # Guard against pathological nesting; real payloads are shallow.
        if depth > 4:
            return
        if isinstance(node, dict):
            if "bookmakerOdds" in node:
                fixtures.append(node)
                return
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(payload)
    return fixtures


def collect(fixtures: list):
    """Walk every fixture once and gather what both probes need."""
    all_books = {}                        # slug -> sample book_data
    market_books = defaultdict(set)       # market_id -> {bookmaker slugs}
    market_shapes = defaultdict(list)     # market_id -> [sorted price tuples]
    betslip_hits = []                     # (slug, market_id, url)

    for fixture in fixtures:
        books = fixture.get("bookmakerOdds", {}) or {}
        if not isinstance(books, dict):
            continue

        for slug, book_data in books.items():
            all_books.setdefault(slug, book_data)
            markets = (book_data or {}).get("markets", {}) or {}

            for market_id, market_data in markets.items():
                outcomes = (market_data or {}).get("outcomes", {}) or {}
                prices = []

                for outcome_data in outcomes.values():
                    players = (outcome_data or {}).get("players", {}) or {}
                    player = players.get("0", {}) or {}

                    slip = player.get("betslip")
                    if isinstance(slip, str):
                        lowered = slip.lower()
                        if any(hint in lowered for hint in FTTS_HINTS):
                            if len(betslip_hits) < 5000:
                                betslip_hits.append((slug, market_id, slip[:150]))

                    try:
                        prices.append(float(player.get("price")))
                    except (TypeError, ValueError):
                        continue

                if prices:
                    market_books[market_id].add(slug)
                    if len(market_shapes[market_id]) < MAX_SHAPES_PER_MARKET:
                        market_shapes[market_id].append(tuple(sorted(prices)))

    return all_books, market_books, market_shapes, betslip_hits


def report_payload_shape(payload, fixtures: list) -> None:
    print("=" * 70)
    print("SECTION 0 — PAYLOAD SHAPE")
    print("=" * 70)
    print(f"Top-level type:      {type(payload).__name__}")
    print(f"Fixture records:     {len(fixtures)}")

    tournaments = Counter()
    for fixture in fixtures:
        tournaments[fixture.get("tournamentId")] += 1
    if tournaments:
        print(f"Distinct tournaments: {len(tournaments)}")
        top = tournaments.most_common(12)
        summary = ", ".join(f"{tid}:{count}" for tid, count in top)
        print(f"Top tournamentIds:   {summary}")


def report_bookmakers(all_books: dict) -> bool:
    print()
    print("=" * 70)
    print("SECTION A — BOOKMAKER ROSTER")
    print("=" * 70)
    slugs = sorted(all_books.keys())
    print(f"Total distinct bookmakers: {len(slugs)}")

    matches = [s for s in slugs if any(h in s.lower() for h in SKY_HINTS)]
    if matches:
        print(f"\n*** SKY BET CANDIDATES FOUND: {matches} ***")
        for slug in matches:
            markets = (all_books.get(slug) or {}).get("markets", {}) or {}
            active = (all_books.get(slug) or {}).get("bookmakerIsActive")
            print(f"    {slug}: {len(markets)} markets in sample, active={active}")
    else:
        print("\n*** NO SKY BET SLUG FOUND ***")
        print("    Full roster for manual review:")
        for i in range(0, len(slugs), 4):
            print("      " + "  ".join(f"{s:<22}" for s in slugs[i:i + 4]))

    return bool(matches)


def report_betslip_hits(betslip_hits: list) -> bool:
    print()
    print("=" * 70)
    print("SECTION B — FTTS SEARCH, METHOD 1: BETSLIP URL KEYWORDS")
    print("=" * 70)

    if not betslip_hits:
        print("No betslip URLs matched any FTTS keyword.")
        return False

    by_market = defaultdict(list)
    for slug, market_id, url in betslip_hits:
        by_market[market_id].append((slug, url))

    print(f"{len(betslip_hits)} keyword hits across {len(by_market)} market IDs.")
    print("Read these by eye — 'first goalscorer' is a PLAYER market, not FTTS.\n")
    for market_id, entries in sorted(by_market.items(), key=lambda kv: -len(kv[1]))[:25]:
        books = {slug for slug, _ in entries}
        print(f"  Market {market_id} — {len(entries)} hits, {len(books)} books")
        print(f"      {entries[0][1]}")
    return True


def report_price_shapes(market_books: dict, market_shapes: dict) -> bool:
    print()
    print("=" * 70)
    print("SECTION C — FTTS SEARCH, METHOD 2: PRICE SHAPE")
    print("=" * 70)
    print(f"Markets carried by >= {MIN_BOOKS_FOR_CANDIDATE} books, 2-3 outcomes,")
    print(f"longest price >= ${LONG_OUTCOME_FLOOR:.2f} (the 'No Goal' signature).\n")

    candidates = []
    for market_id, slugs in market_books.items():
        if len(slugs) < MIN_BOOKS_FOR_CANDIDATE:
            continue

        shapes = market_shapes[market_id]
        if not shapes:
            continue

        modal_count = Counter(len(s) for s in shapes).most_common(1)[0][0]
        if modal_count not in (2, 3):
            continue

        usable = [s for s in shapes if len(s) == modal_count]
        med = [median(s[i] for s in usable) for i in range(modal_count)]
        if med[-1] < LONG_OUTCOME_FLOOR:
            continue

        candidates.append((len(slugs), market_id, modal_count, med, len(usable)))

    if not candidates:
        print("No markets matched the FTTS price signature.")
        print("NOTE: market 101 (1X2) should NOT appear here — its draw price is short.")
        return False

    candidates.sort(reverse=True)
    for book_count, market_id, outcome_count, med, sample in candidates[:30]:
        prices = "  ".join(f"${p:.2f}" for p in med)
        print(f"  Market {market_id:<8} {book_count:>3} books  {outcome_count} outcomes"
              f"  n={sample:<5} median (low->high): {prices}")
    return True


def main() -> None:
    path = find_payload()
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"Reading {path.name} ({size_mb:.1f} MB) — this takes a few seconds...\n")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    fixtures = extract_fixtures(payload)
    if not fixtures:
        sys.exit("ERROR: no fixture records with 'bookmakerOdds' found in this file.")

    all_books, market_books, market_shapes, betslip_hits = collect(fixtures)

    report_payload_shape(payload, fixtures)
    sky_found = report_bookmakers(all_books)
    slip_found = report_betslip_hits(betslip_hits)
    shape_found = report_price_shapes(market_books, market_shapes)

    print()
    print("=" * 70)
    print("PROBE COMPLETE")
    print("=" * 70)
    print(f"  Fixtures parsed:        {len(fixtures)}")
    print(f"  Sky Bet in feed:        {'YES' if sky_found else 'NO'}")
    print(f"  FTTS betslip evidence:  {'YES — review Section B' if slip_found else 'NO'}")
    print(f"  FTTS shape candidates:  {'YES — review Section C' if shape_found else 'NO'}")
    print(f"  Total markets seen:     {len(market_books)}")
    print("  API requests used:      0")


if __name__ == "__main__":
    main()