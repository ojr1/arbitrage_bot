# scripts/freeze_bot/inspect_markets.py
"""
Targeted market inspector for the Freeze bot. Costs ZERO API requests.

Section C of offline_probe.py sorts prices, which discards outcome ordering
and leaves FTTS indistinguishable from a half-time 1X2. This script restores
the ordering and adds two further signals:

  - bookmakerOutcomeId strings (Betsson-style IDs end -home / -draw / -away)
  - betslip deep-link URLs (open one and the bookmaker names the market)

Usage:
    python scripts/freeze_bot/inspect_markets.py <payload.json>
    python scripts/freeze_bot/inspect_markets.py <payload.json> 10211 10208
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Candidates carried forward from offline_probe.py Section C.
DEFAULT_MARKETS = ["10208", "10211", "10216", "10764", "102429", "10152"]

# How many bookmakers to show in full per market.
BOOKS_TO_SHOW = 6

# Labels that would reveal a market's identity inside an outcome ID.
ID_LABELS = ("home", "draw", "away", "no", "none", "first", "score", "half", "ht")


def load_payload(path_arg: str) -> dict:
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


def outcome_sort_key(outcome_id: str):
    """Sort outcome IDs numerically where possible, so 101/102/103 stay in order."""
    try:
        return (0, int(outcome_id))
    except (TypeError, ValueError):
        return (1, str(outcome_id))


def read_outcomes(market_data: dict) -> list:
    """Return [(outcome_id, price, bookmakerOutcomeId, playerName, betslip)] in ID order."""
    outcomes = (market_data or {}).get("outcomes", {}) or {}
    rows = []
    for outcome_id in sorted(outcomes.keys(), key=outcome_sort_key):
        players = (outcomes[outcome_id] or {}).get("players", {}) or {}
        player = players.get("0", {}) or {}
        rows.append((
            outcome_id,
            player.get("price"),
            player.get("bookmakerOutcomeId"),
            player.get("playerName"),
            player.get("betslip"),
        ))
    return rows


def betslip_availability(books: dict) -> None:
    """Report how often betslip URLs are populated at all."""
    print("=" * 74)
    print("BETSLIP URL AVAILABILITY")
    print("=" * 74)

    total = 0
    populated = 0
    sample = None
    for book_data in books.values():
        for market_data in ((book_data or {}).get("markets", {}) or {}).values():
            for outcome_id, price, bm_id, name, slip in read_outcomes(market_data):
                total += 1
                if isinstance(slip, str) and slip.strip():
                    populated += 1
                    if sample is None:
                        sample = slip

    pct = (populated / total * 100) if total else 0.0
    print(f"Outcomes with a betslip URL: {populated:,} of {total:,} ({pct:.1f}%)")
    if sample:
        print(f"Example URL: {sample[:200]}")
    else:
        print("No betslip URLs present anywhere — that detection method is unavailable.")
    print()


def inspect_market(books: dict, market_id: str) -> None:
    print("=" * 74)
    print(f"MARKET {market_id}")
    print("=" * 74)

    carrying = []
    for slug, book_data in books.items():
        markets = (book_data or {}).get("markets", {}) or {}
        if market_id in markets:
            carrying.append((slug, markets[market_id]))

    if not carrying:
        print("Not carried by any bookmaker in this payload.\n")
        return

    print(f"Carried by {len(carrying)} bookmakers.\n")

    # Prefer books whose outcome IDs are descriptive strings — they name the market.
    def informativeness(entry):
        _, market_data = entry
        rows = read_outcomes(market_data)
        return -sum(1 for r in rows if isinstance(r[2], str) and not r[2].isdigit())

    carrying.sort(key=informativeness)

    for slug, market_data in carrying[:BOOKS_TO_SHOW]:
        print(f"  --- {slug} ---")
        for outcome_id, price, bm_id, name, slip in read_outcomes(market_data):
            price_text = f"${float(price):.2f}" if price not in (None, "") else "n/a"
            print(f"    outcome {outcome_id:<10} {price_text:<9} "
                  f"bookmakerOutcomeId={bm_id}")
            if name:
                print(f"        playerName: {name}")
            if isinstance(slip, str) and slip.strip():
                print(f"        betslip: {slip[:170]}")
        print()

    # Scan every carrying book's outcome IDs for identifying keywords.
    hits = Counter()
    for slug, market_data in carrying:
        for outcome_id, price, bm_id, name, slip in read_outcomes(market_data):
            text = f"{bm_id} {name}".lower()
            for label in ID_LABELS:
                if label in text:
                    hits[label] += 1

    if hits:
        summary = ", ".join(f"{label}={count}" for label, count in hits.most_common())
        print(f"  Keyword hits across all {len(carrying)} books: {summary}")
        if hits.get("draw"):
            print("  >>> 'draw' present — this is a 1X2-type market, NOT FTTS.")
    else:
        print("  No identifying keywords found in outcome IDs or player names.")
    print()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/freeze_bot/inspect_markets.py <payload.json> [market_ids...]")

    payload = load_payload(sys.argv[1])
    books = payload.get("bookmakerOdds", {}) or {}
    markets = sys.argv[2:] or DEFAULT_MARKETS

    print(f"Fixture {payload.get('fixtureId')} | tournament {payload.get('tournamentId')} "
          f"| {len(books)} bookmakers\n")

    betslip_availability(books)

    for market_id in markets:
        inspect_market(books, market_id)

    print("=" * 74)
    print("INSPECTION COMPLETE — API requests used: 0")
    print("=" * 74)


if __name__ == "__main__":
    main()