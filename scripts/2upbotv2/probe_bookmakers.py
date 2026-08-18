# scripts/2upbotv2/probe_bookmakers.py
"""
One-off reconnaissance script for 2upbotv2.

Calls OddsPapi /odds?fixtureId=X, which returns every bookmaker for a single
fixture, and answers three questions:

  1. What is the exact slug for bet365, Paddy Power, BetMGM, betfair-ex?
  2. Does OddsPapi expose a SEPARATE "2 Up" style market at all?
  3. What does a full record for each candidate book actually look like?

Request cost: 2 (or 1 if --fixture-id is supplied).
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# --------------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------------

BASE_URL = "https://api.oddspapi.io/v4"

# Confirmed from a live 401 response body on 16 Aug 2026:
# OddsPapi wants the key as the 'apiKey' QUERY PARAMETER, not a header.
AUTH_MODE = "query"
AUTH_KEY_NAME = "apiKey"

# Observed rate limit is roughly 0.54s per endpoint. We pad it slightly.
RATE_DELAY = 0.75

# Default league to pull a sample fixture from: 17 = Premier League (ENG).
DEFAULT_TOURNAMENT_ID = 17

# Below this many characters, the /odds response is treated as empty and no
# conclusions are drawn from it.
MIN_MEANINGFUL_PAYLOAD = 1000

# Slug variants to hunt for. We do not know the exact spelling OddsPapi uses,
# so we test several forms of each name.
CANDIDATE_BOOKS = {
    "bet365": "PRIMARY - 2Up baked into the standard match-odds price",
    "paddypower": "TARGET - 2Up expected as a separate market",
    "paddy-power": "TARGET - 2Up expected as a separate market",
    "paddy_power": "TARGET - 2Up expected as a separate market",
    "betmgm": "TARGET - 2Up expected as a separate market",
    "bet-mgm": "TARGET - 2Up expected as a separate market",
    "betfair-ex": "EXCHANGE - lay side reference",
    "betfairex": "EXCHANGE - lay side reference",
}

# Strings that would indicate a separate early-payout market exists in the
# feed. Searched case-insensitively across the entire flattened response.
PROMO_KEYWORDS = [
    "2up", "2 up", "two up", "2-up",
    "early payout", "earlypayout", "early_payout", "early-payout",
    "goals ahead", "two goals", "goal ahead",
    "insurance", "payout",
]

# Project root is two levels up from this file (scripts/2upbotv2/ -> root).
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"

# --------------------------------------------------------------------------
# HTTP HELPER
# --------------------------------------------------------------------------


def make_request(path, params, api_key):
    """
    Perform one GET request against OddsPapi.

    Always prints the response body on failure - OddsPapi explains its own
    errors clearly, and the status code alone is not enough to debug from.
    """
    url = f"{BASE_URL}{path}"
    headers = {}
    query = dict(params)

    if AUTH_MODE == "header":
        headers[AUTH_KEY_NAME] = api_key
    elif AUTH_MODE == "query":
        query[AUTH_KEY_NAME] = api_key
    else:
        print(f"ERROR: AUTH_MODE must be 'header' or 'query', got '{AUTH_MODE}'.")
        sys.exit(1)

    print(f"  -> GET {path}  params={params}")

    try:
        response = requests.get(url, headers=headers, params=query, timeout=30)
    except requests.RequestException as exc:
        print(f"  !! Network error: {exc}")
        sys.exit(1)

    if response.status_code != 200:
        print(f"  !! HTTP {response.status_code}")
        print(f"  !! Body: {response.text[:1000]}")
        if response.status_code in (401, 403):
            print("  !! Auth rejected. Check AUTH_MODE and AUTH_KEY_NAME "
                  "against core.py.")
        sys.exit(1)

    time.sleep(RATE_DELAY)
    return response.json()


# --------------------------------------------------------------------------
# STEP 1: FIND A USABLE SAMPLE FIXTURE
# --------------------------------------------------------------------------


def parse_start_time(value):
    """Convert an ISO timestamp string to a timezone-aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def find_sample_fixture(tournament_id, api_key):
    """
    Return the fixtureId of the SOONEST UPCOMING fixture that actually has
    odds attached.

    OddsPapi returns full history oldest-first, so taking the first record
    lands on a match from two seasons ago with no odds at all.
    """
    print(f"\n[1] Finding a sample fixture in tournament {tournament_id}...")

    payload = make_request("/fixtures", {"tournamentId": tournament_id}, api_key)

    # The payload may be a bare list or a dict wrapping one. Handle both.
    if isinstance(payload, dict):
        fixtures = (payload.get("data")
                    or payload.get("fixtures")
                    or payload.get("results")
                    or [])
    else:
        fixtures = payload

    print(f"  ..  {len(fixtures)} fixtures returned in total")

    if not fixtures:
        print("  !! No fixtures returned. Try a different --tournament-id.")
        sys.exit(1)

    now = datetime.now(timezone.utc)

    # Keep only fixtures that are still in the future.
    future = []
    for item in fixtures:
        start = parse_start_time(item.get("startTime"))
        if start and start > now:
            future.append((start, item))

    print(f"  ..  {len(future)} are in the future")

    if not future:
        print("  !! Every fixture returned is in the past.")
        print("     The season may not have started for this tournament.")
        sys.exit(1)

    future.sort(key=lambda pair: pair[0])

    # Prefer one that the feed says has odds attached.
    with_odds = [pair for pair in future if pair[1].get("hasOdds") is True]
    print(f"  ..  {len(with_odds)} of those report hasOdds = true")

    if with_odds:
        start, chosen = with_odds[0]
    else:
        start, chosen = future[0]
        print("  !! WARNING: no upcoming fixture reports hasOdds = true.")
        print("     Falling back to the soonest fixture regardless. The odds")
        print("     response may well come back empty.")

    fixture_id = chosen.get("fixtureId") or chosen.get("id")

    if not fixture_id:
        print("  !! Could not locate a fixtureId field. Record was:")
        print(json.dumps(chosen, indent=2)[:1500])
        sys.exit(1)

    print(f"  OK  Using fixtureId {fixture_id}")
    print(f"      Kick-off: {start.isoformat()}")
    print(f"      hasOdds:  {chosen.get('hasOdds')}")
    return fixture_id


# --------------------------------------------------------------------------
# STEP 2: INSPECTION HELPERS
# --------------------------------------------------------------------------

BOOKMAKER_KEYS = ("bookmaker", "bookmakerslug", "bookmakername",
                  "bookmakerkey", "bookmakerid", "slug", "bookie")

MARKET_KEYS = ("market", "marketname", "markettype", "marketkey",
               "markettitle", "bettype", "bet_type", "markets")


def collect_values(node, target_keys, found):
    """
    Recursively walk the JSON collecting string values that sit under any of
    the given key names.

    Recursive means the function calls itself to go one level deeper, the
    same way you drill into nested folders.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in target_keys and isinstance(value, str):
                found.add(value)
            collect_values(value, target_keys, found)
    elif isinstance(node, list):
        for item in node:
            collect_values(item, target_keys, found)


def find_book_records(node, wanted_lower, results):
    """
    Find dictionaries that identify themselves as one of our candidate books,
    so we can print a complete example record for each.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if (key.lower() in BOOKMAKER_KEYS
                    and isinstance(value, str)
                    and value.lower() in wanted_lower):
                results.setdefault(value.lower(), node)
        for value in node.values():
            find_book_records(value, wanted_lower, results)
    elif isinstance(node, list):
        for item in node:
            find_book_records(item, wanted_lower, results)


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Probe OddsPapi for bookmakers and market types on one fixture."
    )
    parser.add_argument("--fixture-id", type=str, default=None,
                        help="Skip the fixture lookup and probe this ID directly "
                             "(saves one request). IDs are strings, e.g. "
                             "id1000001750849967")
    parser.add_argument("--tournament-id", type=int,
                        default=DEFAULT_TOURNAMENT_ID,
                        help="League to draw a sample fixture from.")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.getenv("ODDSPAPI_API_KEY")

    if not api_key:
        print("ERROR: ODDSPAPI_API_KEY not found.")
        print(f"       Expected it in {ROOT / '.env'}")
        sys.exit(1)

    print("=" * 70)
    print("2upbotv2 - BOOKMAKER AND MARKET PROBE")
    print("=" * 70)
    print(f"Auth mode: {AUTH_MODE} ({AUTH_KEY_NAME})")

    requests_used = 0

    if args.fixture_id:
        fixture_id = args.fixture_id
        print(f"\n[1] Skipping lookup, using supplied fixtureId {fixture_id}")
    else:
        fixture_id = find_sample_fixture(args.tournament_id, api_key)
        requests_used += 1

    print(f"\n[2] Fetching all bookmakers for fixtureId {fixture_id}...")
    payload = make_request("/odds", {"fixtureId": fixture_id}, api_key)
    requests_used += 1

    # Save the raw response for later inspection.
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = RAW_DIR / f"probe_bookmakers_{fixture_id}_{stamp}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"  OK  Raw response saved to {out_path}")

    flat = json.dumps(payload).lower()
    print(f"  OK  Payload size: {len(flat):,} characters")

    # A tiny payload means we learned nothing. Show it in full rather than
    # letting the sections below imply a conclusion.
    if len(flat) < 2000:
        print("\n  !! PAYLOAD IS VERY SMALL - printing it in full:")
        print(json.dumps(payload, indent=2))

    # ---- Bookmakers ------------------------------------------------------
    books = set()
    collect_values(payload, BOOKMAKER_KEYS, books)
    book_names = sorted(books)

    print("\n" + "=" * 70)
    print(f"BOOKMAKERS FOUND: {len(book_names)}")
    print("=" * 70)
    if book_names:
        for name in book_names:
            print(f"  {name}")
    else:
        print("  None detected.")

    # ---- Candidate check -------------------------------------------------
    print("\n" + "=" * 70)
    print("CANDIDATE BOOK CHECK")
    print("=" * 70)
    lowered = {n.lower(): n for n in book_names}
    for candidate, note in CANDIDATE_BOOKS.items():
        if candidate in lowered:
            print(f"  PRESENT  {lowered[candidate]:<14} {note}")
        else:
            print(f"  absent   {candidate:<14} -")

    # ---- Market types ----------------------------------------------------
    markets = set()
    collect_values(payload, MARKET_KEYS, markets)
    market_names = sorted(markets)

    print("\n" + "=" * 70)
    print(f"MARKET LABELS FOUND: {len(market_names)}")
    print("=" * 70)
    if market_names:
        for name in market_names:
            print(f"  {name}")
    else:
        print("  None detected.")

    # ---- 2Up keyword sweep ----------------------------------------------
    print("\n" + "=" * 70)
    print("2UP / EARLY PAYOUT KEYWORD SWEEP")
    print("=" * 70)

    if len(flat) < MIN_MEANINGFUL_PAYLOAD:
        print("  INCONCLUSIVE - the response is too small to contain odds.")
        print("  Nothing can be concluded about 2Up market availability.")
        print("  Re-run against a fixture that genuinely has odds.")
    else:
        hits = [kw for kw in PROMO_KEYWORDS if kw in flat]
        if hits:
            print("  HITS: " + ", ".join(hits))
            print("  -> A separate early-payout market may be present.")
            print("  -> Open the saved JSON and search for these terms.")
        else:
            print("  NO HITS in a populated response.")
            print("  -> OddsPapi appears to carry standard markets only.")
            print("  -> Paddy Power / BetMGM 2Up would NOT be reachable here.")

    # ---- Sample records --------------------------------------------------
    print("\n" + "=" * 70)
    print("SAMPLE RECORD PER CANDIDATE BOOK")
    print("=" * 70)
    records = {}
    find_book_records(payload, set(CANDIDATE_BOOKS.keys()), records)
    if records:
        for slug, record in records.items():
            print(f"\n--- {slug} ---")
            print(json.dumps(record, indent=2)[:900])
    else:
        print("  No candidate book records isolated.")

    print("\n" + "=" * 70)
    print(f"PROBE COMPLETE - {len(book_names)} bookmakers, "
          f"{len(market_names)} market labels, "
          f"{requests_used} requests used")
    print("=" * 70)


if __name__ == "__main__":
    main()