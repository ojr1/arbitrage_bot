# scripts/freeze_bot/list_all_tournaments.py
"""
Dumps every soccer tournament from OddsPapi to CSV, then shortlists the
Sky Bet Acca Freeze eligible competitions.

Costs EXACTLY 1 OddsPapi request.

Reads SPORT_ID_SOCCER from scripts/2up_bot/list_tournaments.py rather than
hardcoding it, so there is no guessed value anywhere in this file.

Writes data/tournaments_all.csv (filter it in Excel).

Usage:
    python scripts/freeze_bot/list_all_tournaments.py
    python scripts/freeze_bot/list_all_tournaments.py --all
"""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

API_KEY = os.getenv("ODDSPAPI_API_KEY")
BASE_URL = "https://api.oddspapi.io/v4"
SOURCE_SCRIPT = PROJECT_ROOT / "scripts" / "2up_bot" / "list_tournaments.py"
OUTPUT_PATH = PROJECT_ROOT / "data" / "tournaments_all.csv"

# Search terms for the 36 freeze-eligible competitions. Deliberately loose —
# we print every match and you confirm by eye. The feed names leagues
# inconsistently (LaLiga, La Liga, Primera Division all appear in the wild).
SEARCH_TERMS = [
    "Premier League", "Championship", "League One", "League Two",
    "National League", "FA Cup", "EFL Cup", "Community Shield",
    "Premiership",
    "LaLiga", "La Liga", "Segunda", "Supercopa",
    "Serie A", "Serie B", "Supercoppa",
    "Bundesliga", "Supercup", "Super Cup",
    "Ligue 1", "Ligue 2", "Trophee", "Champions Trophy",
    "Eredivisie", "Eerste Divisie",
    "Primeira Liga", "Jupiler", "Pro League",
    "Super Lig", "Superlig",
    "Brasileiro", "Primera Division", "Liga Profesional",
    "MLS", "Major League Soccer", "A-League", "A League",
    "Champions League", "Europa League", "Conference League",
    "Club World Cup",
]

# Noise filters. The feed carries simulated and youth competitions with
# league-like names — the trap flagged on 15 August.
NOISE = (
    "simulated", "virtual", "esoccer", "srl",
    "women", "u17", "u18", "u19", "u20", "u21", "u23",
    "reserve", "youth", "junior", "qualification", "friendly",
)


def read_sport_id() -> str:
    """Extract SPORT_ID_SOCCER from the working 2up_bot script."""
    if not SOURCE_SCRIPT.exists():
        sys.exit(f"ERROR: cannot find {SOURCE_SCRIPT} to read SPORT_ID_SOCCER from.")

    text = SOURCE_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    match = re.search(r"SPORT_ID_SOCCER\s*=\s*[\"']?([A-Za-z0-9_.-]+)[\"']?", text)
    if not match:
        sys.exit(
            f"ERROR: SPORT_ID_SOCCER not found in {SOURCE_SCRIPT.name}.\n"
            "       Paste me that line and I'll adjust."
        )
    value = match.group(1)
    print(f"  SPORT_ID_SOCCER = {value}  (read from {SOURCE_SCRIPT.name})")
    return value


def fetch(sport_id: str):
    url = f"{BASE_URL}/tournaments"
    params = {"apiKey": API_KEY, "sportId": sport_id}
    print(f"  GET {url}  (sportId={sport_id})")

    try:
        response = requests.get(url, params=params, timeout=60)
    except requests.RequestException as error:
        sys.exit(f"NETWORK ERROR: {error}")

    print(f"  HTTP {response.status_code}  ({len(response.content):,} bytes)")
    if response.status_code != 200:
        sys.exit(f"  Body: {response.text[:400]}")

    payload = response.json()
    # The list may sit at the top level or under a wrapper key.
    if isinstance(payload, dict):
        for key in ("data", "tournaments", "results", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
        sys.exit(f"  Unexpected shape. Top-level keys: {list(payload.keys())[:10]}")
    if isinstance(payload, list):
        return payload
    sys.exit("  Unexpected payload type.")


def field(record: dict, *names, default=""):
    """Return the first populated value among several possible key spellings."""
    for name in names:
        value = record.get(name)
        if value not in (None, ""):
            return value
    return default


def normalise(records: list) -> list:
    rows = []
    for record in records:
        if not isinstance(record, dict):
            continue
        rows.append({
            "tournament_id": field(record, "tournamentId", "id"),
            "name": str(field(record, "tournamentName", "name")),
            "category": str(field(record, "categoryName", "category", "countryName")),
            "future_fixtures": field(record, "futureFixtures", "future", default=""),
        })
    rows.sort(key=lambda r: (r["category"].lower(), r["name"].lower()))
    return rows


def is_noise(row: dict) -> bool:
    text = f"{row['name']} {row['category']}".lower()
    return any(token in text for token in NOISE)


def write_csv(rows: list) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = ["tournament_id", "name", "category", "future_fixtures"]
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def report_matches(rows: list, include_noise: bool) -> None:
    print()
    print("=" * 88)
    print("FREEZE-ELIGIBLE CANDIDATES  (confirm by eye — names overlap across countries)")
    print("=" * 88)

    seen = set()
    for term in SEARCH_TERMS:
        matches = [
            r for r in rows
            if term.lower() in r["name"].lower()
            and (include_noise or not is_noise(r))
        ]
        if not matches:
            continue

        print(f"\n  --- '{term}' ---")
        for row in matches[:14]:
            key = row["tournament_id"]
            marker = " " if key in seen else "*"
            seen.add(key)
            print(f"   {marker} {str(row['tournament_id']):<9}"
                  f"{row['name'][:40]:<42}{row['category'][:22]}")
        if len(matches) > 14:
            print(f"     ... {len(matches) - 14} more — see the CSV")


def main() -> None:
    if not API_KEY:
        sys.exit(f"ERROR: ODDSPAPI_API_KEY not found in {PROJECT_ROOT / '.env'}")

    include_noise = "--all" in sys.argv

    print("=" * 88)
    print("TOURNAMENT DUMP — budget: 1 request")
    print("=" * 88)

    sport_id = read_sport_id()
    records = fetch(sport_id)
    rows = normalise(records)
    write_csv(rows)

    report_matches(rows, include_noise)

    print()
    print("=" * 88)
    print(f"  Tournaments returned: {len(rows)}")
    print(f"  Written to:           {OUTPUT_PATH}")
    print("  Requests used:        1")
    print("=" * 88)


if __name__ == "__main__":
    main()