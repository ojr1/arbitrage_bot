# scripts/2upbotv2/map_markets.py
"""
Offline market identifier for 2upbotv2.

The OddsPapi feed carries no market NAMES, only numeric market IDs. This
script works out what those IDs mean without spending a single API request,
using two ideas:

  1. FREQUENCY. The standard full-time result market appears in nearly every
     bookmaker with exactly 3 outcomes. Counting how many books carry each
     3-outcome market ID sorts the common (standard) from the rare
     (promotional or niche).

  2. BETSLIP LINKS. Each outcome carries a deep link to the bookmaker's own
     page. Opening one in a browser lets the bookmaker name the market for us.

Reads a saved payload from data/raw/. Makes NO API requests.
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

# --------------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------------

# Project root is two levels up from this file (scripts/2upbotv2/ -> root).
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
OUT_DIR = ROOT / "outputs"

# Books we care about for 2upbotv2.
FOCUS_BOOKS = ["bet365", "paddypower", "betmgm", "betfair-ex"]

# How many entries to show in the frequency ranking.
TOP_N = 20

# Only markets with this many outcomes are candidates for a football
# home/draw/away result market.
RESULT_OUTCOME_COUNT = 3

# --------------------------------------------------------------------------
# FILE SELECTION
# --------------------------------------------------------------------------


def newest_raw_file():
    """Return the most recently modified probe payload in data/raw/."""
    candidates = sorted(
        RAW_DIR.glob("probe_bookmakers_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        print(f"ERROR: No probe_bookmakers_*.json found in {RAW_DIR}")
        print("       Run probe_bookmakers.py first.")
        sys.exit(1)
    return candidates[0]


# --------------------------------------------------------------------------
# EXTRACTION
# --------------------------------------------------------------------------


def outcome_price(outcome):
    """
    Pull the price out of one outcome.

    Structure is outcomes -> {outcomeId} -> players -> "0" -> price.
    The 'players' layer exists because the same shape serves player props,
    where there would be more than one entry.
    """
    players = outcome.get("players") or {}
    first = players.get("0")
    if not isinstance(first, dict):
        # Fall back to whatever the first player entry is.
        for value in players.values():
            if isinstance(value, dict):
                first = value
                break
    if not isinstance(first, dict):
        return None, None
    return first.get("price"), first.get("betslip")


def summarise_market(market):
    """Return outcome count, list of prices, and the first betslip link."""
    outcomes = market.get("outcomes") or {}
    prices = []
    betslip = None
    for outcome_id in sorted(outcomes.keys()):
        price, link = outcome_price(outcomes[outcome_id])
        prices.append((outcome_id, price))
        if betslip is None and link:
            betslip = link
    return len(outcomes), prices, betslip


def build_index(payload):
    """
    Flatten the payload into:
        index[book_slug][market_id] = {count, prices, betslip, active}
    """
    index = defaultdict(dict)
    book_odds = payload.get("bookmakerOdds") or {}

    for slug, book in book_odds.items():
        if not isinstance(book, dict):
            continue
        markets = book.get("markets") or {}
        for market_id, market in markets.items():
            if not isinstance(market, dict):
                continue
            count, prices, betslip = summarise_market(market)
            index[slug][market_id] = {
                "count": count,
                "prices": prices,
                "betslip": betslip,
                "active": market.get("marketActive"),
            }
    return index


# --------------------------------------------------------------------------
# REPORT SECTIONS
# --------------------------------------------------------------------------


def format_prices(prices, limit=4):
    """Render a short list of outcomeId:price pairs."""
    shown = prices[:limit]
    text = ", ".join(
        f"{oid}={price}" for oid, price in shown if price is not None
    )
    if len(prices) > limit:
        text += ", ..."
    return text or "(no prices)"


def report_frequency(index, outcome_count, lines):
    """Rank market IDs by how many bookmakers carry them."""
    counter = Counter()
    example = {}

    for slug, markets in index.items():
        for market_id, info in markets.items():
            if info["count"] == outcome_count:
                counter[market_id] += 1
                example.setdefault(market_id, (slug, info))

    lines.append("")
    lines.append("=" * 70)
    lines.append(f"MARKET IDs WITH EXACTLY {outcome_count} OUTCOMES, "
                 f"RANKED BY BOOK COUNT")
    lines.append("=" * 70)
    lines.append("  The top entry is almost certainly FULL-TIME RESULT.")
    lines.append("  Rare entries are candidates for promotional markets.")
    lines.append("")

    for market_id, book_count in counter.most_common(TOP_N):
        slug, info = example[market_id]
        lines.append(f"  market {market_id:<10} carried by {book_count:>4} books"
                     f"   e.g. {slug}: {format_prices(info['prices'])}")

    return counter


def report_focus_books(index, lines):
    """List every 3-outcome market for the books we care about."""
    lines.append("")
    lines.append("=" * 70)
    lines.append("FOCUS BOOKS - ALL 3-OUTCOME MARKETS")
    lines.append("=" * 70)

    for slug in FOCUS_BOOKS:
        markets = index.get(slug)
        lines.append("")
        if not markets:
            lines.append(f"  {slug}: NOT PRESENT in this payload")
            continue

        three_way = {
            mid: info for mid, info in markets.items()
            if info["count"] == RESULT_OUTCOME_COUNT
        }
        lines.append(f"  {slug}: {len(markets)} markets total, "
                     f"{len(three_way)} with 3 outcomes")

        for market_id in sorted(three_way.keys()):
            info = three_way[market_id]
            lines.append(f"    market {market_id:<10} active={info['active']}"
                         f"  {format_prices(info['prices'])}")
            if info["betslip"]:
                lines.append(f"      link: {info['betslip']}")


def report_differences(index, lines):
    """Market IDs a target book has that bet365 does not, and vice versa."""
    lines.append("")
    lines.append("=" * 70)
    lines.append("MARKET ID DIFFERENCES vs bet365")
    lines.append("=" * 70)
    lines.append("  A market a target book has but bet365 does not is a")
    lines.append("  candidate for a separate promotional market.")

    base = set(index.get("bet365", {}).keys())
    if not base:
        lines.append("  bet365 not present - cannot compare.")
        return

    for slug in FOCUS_BOOKS:
        if slug == "bet365":
            continue
        markets = index.get(slug)
        lines.append("")
        if not markets:
            lines.append(f"  {slug}: NOT PRESENT")
            continue

        theirs = set(markets.keys())
        only_theirs = sorted(theirs - base)
        only_base = sorted(base - theirs)

        lines.append(f"  {slug}: {len(theirs)} markets "
                     f"({len(theirs & base)} shared with bet365)")
        lines.append(f"    only in {slug} ({len(only_theirs)}): "
                     f"{only_theirs[:30]}")
        lines.append(f"    only in bet365 ({len(only_base)}): "
                     f"{only_base[:30]}")

        # Of the ones unique to this book, which are 3-outcome?
        unique_three = [
            mid for mid in only_theirs
            if markets[mid]["count"] == RESULT_OUTCOME_COUNT
        ]
        lines.append(f"    of those, 3-outcome: {unique_three}")
        for market_id in unique_three[:5]:
            link = markets[market_id]["betslip"]
            if link:
                lines.append(f"      market {market_id} link: {link}")


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Identify OddsPapi market IDs offline. No API requests."
    )
    parser.add_argument("--file", type=str, default=None,
                        help="Path to a saved JSON payload. Defaults to the "
                             "newest probe_bookmakers_*.json in data/raw/.")
    args = parser.parse_args()

    path = Path(args.file) if args.file else newest_raw_file()

    print("=" * 70)
    print("2upbotv2 - MARKET MAPPER (no API requests)")
    print("=" * 70)
    print(f"File: {path}")
    print("Loading...")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    index = build_index(payload)
    print(f"Indexed {len(index)} bookmakers.\n")

    lines = []
    lines.append(f"Source file: {path}")
    lines.append(f"Fixture: {payload.get('fixtureId')} "
                 f"tournament {payload.get('tournamentId')} "
                 f"kick-off {payload.get('startTime')}")
    lines.append(f"Bookmakers indexed: {len(index)}")

    report_frequency(index, RESULT_OUTCOME_COUNT, lines)
    report_focus_books(index, lines)
    report_differences(index, lines)

    text = "\n".join(lines)
    print(text)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "market_map.txt"
    out_path.write_text(text, encoding="utf-8")

    print("\n" + "=" * 70)
    print(f"MAPPING COMPLETE - report saved to {out_path}")
    print("0 API requests used")
    print("=" * 70)


if __name__ == "__main__":
    main()