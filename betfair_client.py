# betfair_client.py
# Direct Betfair Exchange access for 2upbotv2.
#
# ############################################################
# SENSITIVE
# This module authenticates to a real-money Betfair account.
#   - Credentials come from .env via os.getenv. Never hardcoded.
#   - Certificates live in certs/ and are gitignored.
#   - This module READS PRICES ONLY. There is no bet-placement code here
#     and none should ever be added - 2upbotv2 is a signal bot.
# Never paste certs/client-2048.key or .crt anywhere.
# ############################################################
#
# WHY GO DIRECT INSTEAD OF THROUGH ODDSPAPI
#   1. Frees 3-4 OddsPapi requests per run.
#   2. Gives the FULL price ladder, not just the best level, so the bot can
#      work out the true achievable price for laying the whole stake.
#   3. Real liquidity sizes from the source.
#
# THE COST OF GOING DIRECT
# OddsPapi hands over a shared fixtureId guaranteeing that the bet365 price
# and the exchange price refer to the same match. Betfair uses its own market
# IDs and event names, so fixtures must be matched on team names instead.
# That is what team_names.py exists to do safely.
#
# Betfair meters a per-request WEIGHT against a 200-point cap rather than a
# monthly quota, so failed calls here are cheap - unlike OddsPapi.

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

try:
    import betfairlightweight
    from betfairlightweight.filters import market_filter
except ImportError:
    print("ERROR: betfairlightweight is not installed.")
    print("       pip install betfairlightweight")
    sys.exit(1)

from config_v2 import (
    BETFAIR_KEY_ENV_VAR,
    BETFAIR_USERNAME_ENV_VAR,
    BETFAIR_PASSWORD_ENV_VAR,
    BETFAIR_CERT_DIR,
    BETFAIR_PRICE_PROJECTION,
    BETFAIR_MARKETS_PER_BOOK_CALL,
    BETFAIR_MARKET_TYPE,
    FIXTURE_WINDOW_DAYS,
)

PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(PROJECT_ROOT / ".env")

# Betfair's event type ID for football. Stable, but printed by --event-types
# so it can be verified rather than trusted.
EVENT_TYPE_SOCCER = "1"

# The catalogue's human-readable name for the full-time result market.
# Confirmed by test_betfair_odds.py, which matches on exactly this string.
MATCH_ODDS_MARKET_NAME = "Match Odds"


# ─────────────────────────────────────────────
# CONNECTION
# ─────────────────────────────────────────────

def connect(verbose=True):
    """
    Log in to Betfair and return the client.

    CHANGED FROM test_betfair.py: the certificate folder is anchored to this
    file's directory rather than os.getcwd(). The original resolves against
    whatever folder you happen to be standing in, so running the bot from
    scripts/2upbotv2/ would look for certs in the wrong place and fail with a
    confusing SSL error.
    """
    api_key = os.getenv(BETFAIR_KEY_ENV_VAR)
    username = os.getenv(BETFAIR_USERNAME_ENV_VAR)
    password = os.getenv(BETFAIR_PASSWORD_ENV_VAR)

    missing = [
        name for name, value in (
            (BETFAIR_KEY_ENV_VAR, api_key),
            (BETFAIR_USERNAME_ENV_VAR, username),
            (BETFAIR_PASSWORD_ENV_VAR, password),
        ) if not value
    ]
    if missing:
        print(f"ERROR: missing from .env: {', '.join(missing)}")
        sys.exit(1)

    certs_path = PROJECT_ROOT / BETFAIR_CERT_DIR
    if not certs_path.is_dir():
        print(f"ERROR: certificate folder not found: {certs_path}")
        print("       Run generate_certs.py, or check BETFAIR_CERT_DIR.")
        sys.exit(1)

    if verbose:
        # Presence only - never the values themselves.
        print(f"  Credentials loaded: key={bool(api_key)} "
              f"user={bool(username)} pass={bool(password)}")
        print(f"  Certs path: {certs_path}")

    client = betfairlightweight.APIClient(
        username=username,
        password=password,
        app_key=api_key,
        certs=str(certs_path),
    )

    client.login()
    if verbose:
        print("  Login successful")
    return client


# ─────────────────────────────────────────────
# DISCOVERY
# ─────────────────────────────────────────────

def event_types(client):
    """List Betfair's sports, to confirm the football event type ID."""
    results = client.betting.list_event_types()
    return [
        {
            "id": item.event_type.id,
            "name": item.event_type.name,
            "market_count": item.market_count,
        }
        for item in results
    ]


def soccer_competitions(client):
    """
    List every football competition Betfair currently has markets for.

    This is the Betfair equivalent of list_tournaments.py: it produces the IDs
    that must go into config, because Betfair has no idea what OddsPapi's
    tournament 17 means. Re-run each season - IDs can change.
    """
    results = client.betting.list_competitions(
        filter=market_filter(event_type_ids=[EVENT_TYPE_SOCCER])
    )

    rows = []
    for item in results:
        region = getattr(item, "competition_region", None)
        rows.append({
            "id": item.competition.id,
            "name": item.competition.name,
            "region": region or "",
            "market_count": item.market_count,
        })
    return sorted(rows, key=lambda row: (row["region"], row["name"]))


# ─────────────────────────────────────────────
# MARKETS AND PRICES
# ─────────────────────────────────────────────

def match_odds_catalogue(client, competition_ids, window_days=FIXTURE_WINDOW_DAYS):
    """
    Find MATCH_ODDS markets for the given competitions inside the window.

    Returns the catalogue: which markets exist, their event names, kick-off
    times and runner names. No prices yet - that is list_market_book's job.

    Two filters are applied for the same thing: market_type_codes on the
    request, and a check on market_name afterwards. Belt and braces, because
    pricing a market that is not the full-time result would be silent and
    expensive.
    """
    now = datetime.now(timezone.utc)
    finish = now + timedelta(days=window_days)

    results = client.betting.list_market_catalogue(
        filter=market_filter(
            event_type_ids=[EVENT_TYPE_SOCCER],
            competition_ids=[str(cid) for cid in competition_ids],
            market_type_codes=[BETFAIR_MARKET_TYPE],
            market_start_time={
                "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": finish.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        ),
        market_projection=[
            "EVENT",
            "COMPETITION",
            "MARKET_START_TIME",
            "RUNNER_DESCRIPTION",
        ],
        max_results=1000,
        sort="FIRST_TO_START",
    )

    markets = []
    skipped = 0

    for item in results:
        if item.market_name != MATCH_ODDS_MARKET_NAME:
            skipped += 1
            continue

        event = getattr(item, "event", None)
        competition = getattr(item, "competition", None)

        runners = []
        for runner in (item.runners or []):
            runners.append({
                "selection_id": runner.selection_id,
                "name": runner.runner_name,
            })

        markets.append({
            "market_id": item.market_id,
            "market_name": item.market_name,
            "event_id": getattr(event, "id", None),
            "event_name": getattr(event, "name", None),
            "competition_id": getattr(competition, "id", None),
            "competition_name": getattr(competition, "name", None),
            "start_time": (item.market_start_time.isoformat()
                           if item.market_start_time else None),
            "runners": runners,
        })

    if skipped:
        print(f"    ({skipped} markets skipped - not named "
              f"'{MATCH_ODDS_MARKET_NAME}')")

    return markets


def ladder_from_runner(runner):
    """
    Pull both price ladders out of one runner's exchange prices.

    Each ladder is a list of {price, size} levels, best price first. This is
    the whole reason for going direct: v1 saw only the top level and assumed
    it held for the entire stake.
    """
    prices = getattr(runner, "ex", None)

    def levels(source):
        out = []
        for level in (source or []):
            out.append({
                "price": getattr(level, "price", None),
                "size": getattr(level, "size", None),
            })
        return out

    return {
        "available_to_back": levels(getattr(prices, "available_to_back", None)),
        "available_to_lay": levels(getattr(prices, "available_to_lay", None)),
    }


def match_odds_prices(client, market_ids):
    """
    Fetch full price ladders for a list of market IDs.

    CHANGED IN REVISION 2: price_projection is now a plain dictionary, exactly
    as test_betfair_odds.py does it. The previous version built it through
    betfairlightweight's filters helpers, which was a guess at their argument
    names. Proven code beats inferred code.

    Betfair meters a per-request WEIGHT against a 200-point cap. Full-ladder
    data costs more weight per market than best-offers, so markets are sent in
    small batches. BETFAIR_MARKETS_PER_BOOK_CALL is deliberately conservative
    until the real limit is measured on this account - if a batch is rejected
    for weight, lower it.
    """
    price_projection = {"priceData": [BETFAIR_PRICE_PROJECTION]}

    books = {}
    batch_size = BETFAIR_MARKETS_PER_BOOK_CALL
    total_batches = -(-len(market_ids) // batch_size)  # ceiling division

    for index in range(0, len(market_ids), batch_size):
        batch = market_ids[index:index + batch_size]
        batch_number = index // batch_size + 1
        print(f"    batch {batch_number}/{total_batches} "
              f"({len(batch)} markets)")

        try:
            results = client.betting.list_market_book(
                market_ids=batch,
                price_projection=price_projection,
            )
        except Exception as exc:
            print(f"    !! batch failed: {exc}")
            print("       If this mentions weight, lower "
                  "BETFAIR_MARKETS_PER_BOOK_CALL in config_v2.py.")
            continue

        for book in results:
            runners = {}
            for runner in (book.runners or []):
                runners[runner.selection_id] = {
                    "status": runner.status,
                    "last_price_traded": runner.last_price_traded,
                    "total_matched": runner.total_matched,
                    **ladder_from_runner(runner),
                }

            books[book.market_id] = {
                "status": book.status,
                "inplay": book.inplay,
                "bet_delay": book.bet_delay,
                "total_matched": book.total_matched,
                "runners": runners,
            }

    return books


def fetch_match_odds(client, competition_ids, window_days=FIXTURE_WINDOW_DAYS):
    """
    Catalogue plus prices, joined into one list ready for the matcher.

    Each entry carries the Betfair event name and both runner names, which is
    what team_names.py compares against the OddsPapi side.
    """
    print("  Fetching market catalogue...")
    catalogue = match_odds_catalogue(client, competition_ids, window_days)
    print(f"  {len(catalogue)} Match Odds markets found")

    if not catalogue:
        return []

    print("  Fetching price ladders...")
    books = match_odds_prices(client, [m["market_id"] for m in catalogue])

    joined = []
    for market in catalogue:
        book = books.get(market["market_id"])
        if not book:
            continue

        runners = []
        for runner in market["runners"]:
            prices = book["runners"].get(runner["selection_id"], {})
            runners.append({**runner, **prices})

        joined.append({**market,
                       "status": book["status"],
                       "inplay": book["inplay"],
                       "bet_delay": book["bet_delay"],
                       "total_matched": book["total_matched"],
                       "runners": runners})

    return joined


# ─────────────────────────────────────────────
# COMMAND LINE
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Betfair Exchange access for 2upbotv2. Reads prices only."
    )
    parser.add_argument("--event-types", action="store_true",
                        help="List Betfair sports, to confirm the football ID.")
    parser.add_argument("--competitions", action="store_true",
                        help="List football competitions with their IDs.")
    parser.add_argument("--filter", type=str, default="",
                        help="Only show competitions whose name contains this.")
    parser.add_argument("--markets", type=str, default="",
                        help="Comma-separated Betfair competition IDs to fetch "
                             "Match Odds markets and ladders for.")
    parser.add_argument("--save", action="store_true",
                        help="Save fetched markets to data/raw/ as JSON.")
    args = parser.parse_args()

    print("=" * 70)
    print("2upbotv2 - BETFAIR EXCHANGE CLIENT")
    print("=" * 70)

    client = connect()

    if args.event_types:
        print("\nEVENT TYPES")
        for row in event_types(client):
            print(f"  {row['id']:<6} {row['name']:<28} "
                  f"markets={row['market_count']}")

    if args.competitions:
        rows = soccer_competitions(client)
        needle = args.filter.lower()
        if needle:
            rows = [r for r in rows if needle in r["name"].lower()]

        print(f"\nFOOTBALL COMPETITIONS ({len(rows)} shown)")
        for row in rows:
            print(f"  {row['id']:<10} {row['region']:<6} "
                  f"{row['name']:<44} markets={row['market_count']}")

    if args.markets:
        ids = [part.strip() for part in args.markets.split(",") if part.strip()]
        print(f"\nFETCHING MATCH ODDS for competitions {ids}")
        markets = fetch_match_odds(client, ids)

        print(f"\n{len(markets)} markets with prices:")
        for market in markets[:10]:
            print(f"\n  {market['event_name']}  "
                  f"({market['competition_name']}) "
                  f"{market['start_time']}  status={market['status']}")
            for runner in market["runners"]:
                lay = runner.get("available_to_lay") or []
                best = lay[0] if lay else {}
                print(f"    {runner['name']:<32} "
                      f"lay={best.get('price')} size={best.get('size')} "
                      f"levels={len(lay)}")

        if args.save and markets:
            raw_dir = PROJECT_ROOT / "data" / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = raw_dir / f"betfair_markets_{stamp}.json"
            path.write_text(json.dumps(markets, indent=2), encoding="utf-8")
            print(f"\n  Saved to {path}")

    if not (args.event_types or args.competitions or args.markets):
        print("\nNothing requested. Try one of:")
        print("  python betfair_client.py --event-types")
        print("  python betfair_client.py --competitions --filter premier")
        print("  python betfair_client.py --markets 10932509 --save")

    print("\n" + "=" * 70)
    print("BETFAIR CLIENT DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()