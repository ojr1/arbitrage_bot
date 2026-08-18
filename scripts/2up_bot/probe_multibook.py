"""
probe_multibook.py
Location: scripts/2up_bot/probe_multibook.py

ONE-OFF API PROBE - delete once we have the answer.

QUESTION
Does /odds-by-tournaments have to be called once per bookmaker, or can one
call return bet365 AND betfair-ex together?

Right now the bot makes 6 odds calls per run: 2 for bet365 (limit 5 leagues)
and 4 for betfair-ex (limit 3 leagues). If one call can carry both books,
that could drop to 2-4 calls and roughly halve the monthly request cost.

WHAT IT TESTS
  1. bookmaker=bet365                 - baseline, known to work
  2. no bookmaker parameter at all    - does it return everything?
  3. bookmaker=bet365,betfair-ex      - does it accept a list?
  4. whichever of 2 or 3 works, retested with 5 leagues to find the cap

For each it reports the HTTP status, how many fixtures came back, which of
our two books are actually present, and the response size - because "returns
all 350 bookmakers" may be true but enormous.

API cost: about 5 requests.
"""

import os
import json
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

API_KEY  = os.getenv("ODDSPAPI_API_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

THREE_LEAGUES = "17,18,36"          # PL, Championship, Scottish Premiership
FIVE_LEAGUES  = "17,18,36,8,35"     # ...plus LaLiga and Bundesliga

REQUEST_DELAY = 1.5
REQUEST_COUNT = 0


def probe(label, params):
    """Make one call and report what came back."""
    global REQUEST_COUNT
    print(f"\n  {label}")
    print(f"    params: {params}")

    time.sleep(REQUEST_DELAY)
    REQUEST_COUNT += 1

    try:
        response = requests.get(
            f"{BASE_URL}/odds-by-tournaments",
            params={"apiKey": API_KEY, **params},
            timeout=60,
        )
    except Exception as exc:
        print(f"    FAILED: {exc}")
        return False

    size_kb = len(response.content) / 1024
    print(f"    HTTP {response.status_code}   response {size_kb:,.0f} KB")

    if response.status_code != 200:
        print(f"    Error: {response.text[:250]}")
        return False

    try:
        data = response.json()
    except Exception:
        print("    Could not parse JSON")
        return False

    fixtures = data if isinstance(data, list) else []
    print(f"    fixtures: {len(fixtures)}")

    if not fixtures:
        return False

    # Which bookmakers actually appear anywhere in the response?
    books = set()
    tournaments = set()
    for fixture in fixtures:
        books.update(fixture.get("bookmakerOdds", {}).keys())
        if fixture.get("tournamentId"):
            tournaments.add(fixture["tournamentId"])

    has_soft = "bet365" in books
    has_exch = "betfair-ex" in books

    print(f"    distinct bookmakers: {len(books)}")
    print(f"    leagues represented: {sorted(tournaments)}")
    print(f"    bet365 present:      {has_soft}")
    print(f"    betfair-ex present:  {has_exch}   <- the one that matters")

    if len(books) > 2:
        sample = sorted(books)[:12]
        print(f"    sample of books:     {sample}")

    if has_soft and has_exch:
        print("    >> BOTH BOOKS IN ONE CALL")

    return has_soft and has_exch


def main():
    print("\n" + "#" * 70)
    print("#  ODDSPAPI MULTI-BOOKMAKER PROBE")
    print("#" * 70)

    if not API_KEY:
        print("  API key NOT loaded.")
        return

    print("\n" + "=" * 70)
    print("TEST 1 - BASELINE (single bookmaker, as the bot does today)")
    print("=" * 70)
    probe("bet365 only, 3 leagues",
          {"tournamentIds": THREE_LEAGUES, "bookmaker": "bet365"})

    print("\n" + "=" * 70)
    print("TEST 2 - NO BOOKMAKER PARAMETER")
    print("=" * 70)
    no_param_works = probe("no bookmaker, 3 leagues",
                           {"tournamentIds": THREE_LEAGUES})

    print("\n" + "=" * 70)
    print("TEST 3 - COMMA-SEPARATED BOOKMAKERS")
    print("=" * 70)
    list_works = probe("bookmaker=bet365,betfair-ex, 3 leagues",
                       {"tournamentIds": THREE_LEAGUES,
                        "bookmaker": "bet365,betfair-ex"})

    print("\n" + "=" * 70)
    print("TEST 4 - HOW MANY LEAGUES DOES THE WINNING FORM ALLOW?")
    print("=" * 70)

    if list_works:
        probe("bookmaker=bet365,betfair-ex, 5 leagues",
              {"tournamentIds": FIVE_LEAGUES,
               "bookmaker": "bet365,betfair-ex"})
    elif no_param_works:
        probe("no bookmaker, 5 leagues",
              {"tournamentIds": FIVE_LEAGUES})
    else:
        print("\n  Neither multi-book form worked - the bot stays as it is.")

    print("\n" + "=" * 70)
    print(f"DONE - API requests used: {REQUEST_COUNT}")
    print("=" * 70)
    print("\nPaste the output and I will rework the fetch if it is worth it.\n")


if __name__ == "__main__":
    main()