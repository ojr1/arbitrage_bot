# scripts/freeze_bot/probe_endpoint.py
"""
Live probe: does /odds-by-tournaments serve market 10216 (First Team To Score)?

Costs EXACTLY 2 OddsPapi requests. Reads ODDSPAPI_API_KEY from .env.

Question 1: calling without a market filter, which markets come back?
Question 2: calling with marketId=10216 explicitly, does it work?

Usage:
    python scripts/freeze_bot/probe_endpoint.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("ODDSPAPI_API_KEY")
BASE_URL = "https://api.oddspapi.io/v4/odds-by-tournaments"

# Premier League only — one tournament keeps the payload small and readable.
TOURNAMENT_ID = "17"
BOOKMAKER = "paddypower"

MARKET_MATCH_ODDS = "101"
MARKET_FTTS = "10216"

REQUEST_DELAY = 1.5          # matches config.py
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw"


def call(params: dict, label: str):
    """Make one OddsPapi request. Auth goes in the apiKey QUERY PARAMETER."""
    full_params = {"apiKey": API_KEY, **params}
    shown = {k: v for k, v in full_params.items() if k != "apiKey"}
    print(f"  Request: {shown}")

    try:
        response = requests.get(BASE_URL, params=full_params, timeout=60)
    except requests.RequestException as error:
        print(f"  NETWORK ERROR: {error}")
        return None

    print(f"  HTTP {response.status_code}  ({len(response.content):,} bytes)")
    if response.status_code != 200:
        print(f"  Body: {response.text[:400]}")
        return None

    try:
        return response.json()
    except ValueError:
        print("  ERROR: response was not valid JSON")
        return None


def find_fixtures(payload) -> list:
    """Return every dict in the payload that carries market data."""
    found = []

    def walk(node, depth=0):
        if depth > 5:
            return
        if isinstance(node, dict):
            if "bookmakerOdds" in node or "markets" in node:
                found.append(node)
                return
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(payload)
    return found


def markets_in(record: dict) -> dict:
    """Pull the markets dict out of either payload shape."""
    if "markets" in record:
        return record.get("markets", {}) or {}
    books = record.get("bookmakerOdds", {}) or {}
    for book_data in books.values():
        markets = (book_data or {}).get("markets", {}) or {}
        if markets:
            return markets
    return {}


def summarise(payload, label: str) -> set:
    print(f"\n  --- {label} ---")
    if payload is None:
        print("  No payload returned.")
        return set()

    records = find_fixtures(payload)
    print(f"  Fixture records: {len(records)}")

    market_counter = Counter()
    for record in records:
        for market_id in markets_in(record).keys():
            market_counter[market_id] += 1

    if not market_counter:
        print("  No markets found in the response.")
        return set()

    print(f"  Distinct market IDs: {len(market_counter)}")
    top = ", ".join(f"{mid}({n})" for mid, n in market_counter.most_common(12))
    print(f"  Most common: {top}")

    for market_id, name in ((MARKET_MATCH_ODDS, "match odds"), (MARKET_FTTS, "FTTS")):
        status = "PRESENT" if market_id in market_counter else "ABSENT"
        print(f"  Market {market_id} ({name}): {status}")

    return set(market_counter.keys())


def save(payload, filename: str) -> None:
    if payload is None:
        return
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle)
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  Saved: {path.name} ({size_mb:.2f} MB)")


def main() -> None:
    if not API_KEY:
        sys.exit(
            "ERROR: ODDSPAPI_API_KEY not found.\n"
            f"       Expected it in {PROJECT_ROOT / '.env'}"
        )

    print("=" * 74)
    print("ODDSPAPI ENDPOINT PROBE — budget: 2 requests")
    print("=" * 74)

    print("\n[1/2] No market filter — what does the endpoint return by default?")
    payload_a = call(
        {"tournamentIds": TOURNAMENT_ID, "bookmaker": BOOKMAKER},
        "no filter",
    )
    markets_a = summarise(payload_a, "Response A: no market filter")
    save(payload_a, "freeze_probe_nofilter.json")

    time.sleep(REQUEST_DELAY)

    print("\n[2/2] Explicit marketId=10216 — is FTTS servable here?")
    payload_b = call(
        {"tournamentIds": TOURNAMENT_ID, "bookmaker": BOOKMAKER, "marketId": MARKET_FTTS},
        "ftts filter",
    )
    markets_b = summarise(payload_b, "Response B: marketId=10216")
    save(payload_b, "freeze_probe_ftts.json")

    print()
    print("=" * 74)
    print("VERDICT")
    print("=" * 74)

    ftts_unfiltered = MARKET_FTTS in markets_a
    ftts_filtered = MARKET_FTTS in markets_b

    if ftts_unfiltered:
        print("  FTTS IS returned by /odds-by-tournaments without any filter.")
        print("  -> Batch both columns. Whole run costs ~10 requests.")
    elif ftts_filtered:
        print("  FTTS IS servable, but only when marketId is passed explicitly.")
        print("  -> Two batched passes (101 then 10216). Still cheap.")
    else:
        print("  FTTS is NOT available on /odds-by-tournaments.")
        print("  -> FTTS must come from /odds?fixtureId, one call per qualifying")
        print("     fixture. Shortlist first, then price it.")

    print(f"\n  Requests used: 2")


if __name__ == "__main__":
    main()