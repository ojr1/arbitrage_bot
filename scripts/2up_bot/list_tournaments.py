"""
list_tournaments.py
Location: scripts/2up_bot/list_tournaments.py

TOURNAMENT ID FINDER  (Version 5)

Run this whenever you want to ADD a league to the bot, or at the start of each
season to check the existing IDs still point at the right competitions.

WHAT IT DOES
  1. Verifies the leagues already in config.py still resolve correctly.
  2. Lists every tournament for the countries in COUNTRIES below, with how
     many fixtures each currently has, so you can pick new ones.

TO ADD A LEAGUE
  1. Put its country in COUNTRIES below and run this script.
  2. Find the league in the output and note its ID.
  3. Add that ID to TWO_UP_TOURNAMENT_IDS in config.py.
  4. Optionally add a readable name to LEAGUE_NAMES in run.py.
  That is the whole job - no other code changes.

WARNING
  Never pick an ID by name alone. The feed contains "Simulated Reality League"
  and "Virtual Football" entries whose names mimic real competitions but are
  computer simulations. Always check the country column.

API cost: 1 request.
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

SPORT_ID_SOCCER = 10

# Countries to list tournaments for. Add or remove as you please.
# Matched exactly against the feed's categoryName, which conveniently keeps
# "England Amateur" and "Simulated Reality League" out of the results.
COUNTRIES = [
    "England",
    "Scotland",
    "Brazil",
]

# Leagues currently configured in the bot, for the verification table.
CONFIGURED = [
    (17, "Premier League",  "England"),
    (18, "Championship",    "England"),
    (36, "Premiership",     "Scotland"),
    (8,  "LaLiga",          "Spain"),
    (35, "Bundesliga",      "Germany"),
    (23, "Serie A",         "Italy"),
    (34, "Ligue 1",         "France"),
]

REQUEST_DELAY = 1.5


def call_api(endpoint, params, max_retries=2):
    """Call the API. Returns (json_or_None, status_code, error_text)."""
    url = f"{BASE_URL}/{endpoint}"
    params = {"apiKey": API_KEY, **params}

    for attempt in range(max_retries + 1):
        time.sleep(REQUEST_DELAY)
        try:
            response = requests.get(url, params=params, timeout=30)

            if response.status_code == 429:
                wait_ms = 2000
                try:
                    wait_ms = response.json()["error"].get("retryMs", 2000)
                except Exception:
                    pass
                if attempt < max_retries:
                    time.sleep((wait_ms / 1000) + 0.5)
                    continue
                return None, 429, "rate limited"

            if response.status_code != 200:
                return None, response.status_code, response.text[:300]

            return response.json(), 200, ""

        except Exception as exc:
            return None, 0, str(exc)

    return None, 0, "unknown"


def fetch_tournaments():
    data, status, err = call_api("tournaments", {"sportId": SPORT_ID_SOCCER})
    if status != 200:
        print(f"  HTTP {status}: {err}")
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def verify_configured(by_id):
    """Check the IDs already in config.py still point where we think."""
    print("\n" + "=" * 76)
    print("CURRENTLY CONFIGURED LEAGUES")
    print("=" * 76)
    print("  ID      League                Country      Upcoming  Future  Live  Status")
    print("  " + "-" * 74)

    for tid, expected_name, expected_country in CONFIGURED:
        record = by_id.get(tid)
        if not record:
            print(f"  {tid:<7} {expected_name:<21} {'?':<12} "
                  f"{'-':>8}  {'-':>6}  {'-':>4}  ID NOT FOUND")
            continue

        name    = record.get("tournamentName", "?")
        country = record.get("categoryName", "?")
        upc     = record.get("upcomingFixtures", 0)
        fut     = record.get("futureFixtures", 0)
        live    = record.get("liveFixtures", 0)

        ok = (expected_name.lower() in name.lower()
              and expected_country.lower() in country.lower())

        print(f"  {tid:<7} {name[:21]:<21} {country[:12]:<12} "
              f"{upc:>8}  {fut:>6}  {live:>4}  {'ok' if ok else 'MISMATCH'}")


def list_by_country(tournaments):
    """Print every tournament for each country in COUNTRIES."""
    configured_ids = {tid for tid, _, _ in CONFIGURED}

    for country in COUNTRIES:
        matches = [
            t for t in tournaments
            if isinstance(t, dict)
            and str(t.get("categoryName", "")).lower() == country.lower()
        ]

        print("\n" + "=" * 76)
        print(f"{country.upper()}  -  {len(matches)} tournaments")
        print("=" * 76)

        if not matches:
            print("  None found. Check the spelling against the feed's categoryName.")
            continue

        # Busiest first - the ones with fixtures are the ones you want.
        matches.sort(key=lambda t: t.get("futureFixtures", 0), reverse=True)

        print("  ID       League                              Future  Live  In bot")
        print("  " + "-" * 70)
        for t in matches:
            tid  = t.get("tournamentId")
            name = t.get("tournamentName", "?")
            fut  = t.get("futureFixtures", 0)
            live = t.get("liveFixtures", 0)
            mark = "YES" if tid in configured_ids else ""
            print(f"  {str(tid):<8} {name[:35]:<35} {fut:>6}  {live:>4}  {mark}")


def main():
    print("\n" + "#" * 76)
    print("#  TOURNAMENT ID FINDER  (v5)")
    print("#" * 76)

    if not API_KEY:
        print("  API key NOT loaded.")
        return

    tournaments = fetch_tournaments()
    if not tournaments:
        print("  No tournaments returned.")
        return

    by_id = {
        t["tournamentId"]: t
        for t in tournaments
        if isinstance(t, dict) and "tournamentId" in t
    }

    verify_configured(by_id)
    list_by_country(tournaments)

    print("\n" + "=" * 76)
    print("Add the IDs you want to TWO_UP_TOURNAMENT_IDS in config.py.")
    print("Check bet365's 2Up terms cover the league before adding it.")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    main()