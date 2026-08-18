# scripts/freeze_bot/freeze_teams.py
"""
Team-name cache for the Freeze bot.

teams.py already calls /fixtures with only sportId and a date range, then
discards every fixture outside 2up_bot's leagues. This script makes the same
call and keeps the fixtures for the 36 freeze-eligible competitions instead.

Writes its own cache at data/freeze_team_cache.json, so teams.py, its cache,
and both existing bots are untouched.

Usage:
    python scripts/freeze_bot/freeze_teams.py            # refresh if stale
    python scripts/freeze_bot/freeze_teams.py --force    # refresh regardless
    python scripts/freeze_bot/freeze_teams.py --show 40  # print cached names
    python scripts/freeze_bot/freeze_teams.py --status   # zero requests
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import config_freeze as cfg  # noqa: E402

API_KEY = os.getenv("ODDSPAPI_API_KEY")
CACHE_PATH = PROJECT_ROOT / "data" / "freeze_team_cache.json"

# The screener only prices upcoming fixtures, so a short window is enough.
# Kept deliberately small to hold the request cost down.
WINDOW_DAYS = 10

# Days per /fixtures call. Conservative — the API's maximum range is unknown,
# and a rejected call wastes a request. Raise it if the calls succeed easily.
CHUNK_DAYS = 5

# Refresh if the cache is older than this.
MAX_AGE_DAYS = 14

REFRESH_LOOKBACK_DAYS = 1   # yesterday, to catch fixtures already in play


def empty_cache() -> dict:
    return {
        "updated": None,
        "participants": {},   # participantId (as string) -> team name
        "source": "oddspapi /fixtures participant1Name / participant2Name",
        "scope": "freeze-eligible tournaments only",
    }


def load_cache() -> dict:
    if not CACHE_PATH.exists():
        return empty_cache()
    try:
        with CACHE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return empty_cache()
    if not isinstance(data, dict) or "participants" not in data:
        return empty_cache()
    return data


def save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", newline="", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=1, ensure_ascii=False)


def cache_age_days(cache: dict):
    stamp = cache.get("updated")
    if not stamp:
        return None
    try:
        updated = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - updated).total_seconds() / 86400


def is_stale(cache: dict) -> bool:
    if not cache.get("participants"):
        return True
    age = cache_age_days(cache)
    return age is None or age > MAX_AGE_DAYS


def date_chunks(window_days: int, chunk_days: int) -> list:
    start = datetime.now(timezone.utc).date() - timedelta(days=REFRESH_LOOKBACK_DAYS)
    finish = start + timedelta(days=window_days)
    chunks = []
    cursor = start
    while cursor < finish:
        chunk_end = min(cursor + timedelta(days=chunk_days), finish)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end
    return chunks


def call_fixtures(params: dict):
    url = f"{cfg.ODDSPAPI_BASE_URL}/fixtures"
    query = {"apiKey": API_KEY, **params}
    try:
        response = requests.get(url, params=query, timeout=60)
    except requests.RequestException as error:
        print(f"      network error: {error}")
        return None

    if response.status_code != 200:
        print(f"      HTTP {response.status_code}: {response.text[:180]}")
        return None

    try:
        return response.json()
    except ValueError:
        print("      unparseable JSON")
        return None


def walk_fixtures(payload) -> list:
    """Flatten the /fixtures payload into a list of fixture dicts."""
    found = []

    def walk(node, depth=0):
        if depth > 5:
            return
        if isinstance(node, dict):
            if "participant1Id" in node or "fixtureId" in node:
                found.append(node)
                return
            for value in node.values():
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(payload)
    return found


def extract(payload, wanted: set) -> tuple:
    """Return (participantId -> name) for fixtures in our tournaments."""
    found = {}
    skipped = 0

    for fixture in walk_fixtures(payload):
        if fixture.get("tournamentId") not in wanted:
            skipped += 1
            continue
        pairs = (
            (fixture.get("participant1Id"), fixture.get("participant1Name")),
            (fixture.get("participant2Id"), fixture.get("participant2Name")),
        )
        for participant_id, name in pairs:
            if participant_id is None or not name:
                continue
            found[str(participant_id)] = name

    return found, skipped


def refresh() -> dict:
    """
    Fetch names across the freeze leagues and merge into the cache.

    Merges rather than replaces, for the same reason teams.py does: a club
    whose league is between seasons won't appear in the current window, and
    dropping its name would break every fixture referencing it later.
    """
    cache = load_cache()
    before = len(cache.get("participants", {}))
    wanted = set(cfg.FREEZE_TOURNAMENTS.keys())
    chunks = date_chunks(WINDOW_DAYS, CHUNK_DAYS)

    print(f"Refreshing names across {len(wanted)} freeze leagues "
          f"in {len(chunks)} date chunks...")

    requests_used = 0
    total_skipped = 0

    for index, (start, finish) in enumerate(chunks, start=1):
        params = {
            "sportId": cfg.SPORT_ID_SOCCER,
            "from": start.strftime("%Y-%m-%d"),
            "to": finish.strftime("%Y-%m-%d"),
        }
        print(f"  [{index}/{len(chunks)}] {params['from']} to {params['to']}")
        payload = call_fixtures(params)
        requests_used += 1

        if payload is None:
            print("      no data for this chunk")
            continue

        found, skipped = extract(payload, wanted)
        total_skipped += skipped
        cache["participants"].update(found)
        print(f"      {len(found)} teams in freeze leagues "
              f"({skipped} fixtures outside them)")

        if index < len(chunks):
            time.sleep(cfg.REQUEST_DELAY)

    cache["updated"] = datetime.now(timezone.utc).isoformat()
    save_cache(cache)

    after = len(cache["participants"])
    print(f"\n  Teams before: {before}")
    print(f"  Teams after:  {after}  (+{after - before})")
    print(f"  Fixtures skipped (other leagues): {total_skipped}")
    print(f"  Requests used: {requests_used}")
    return cache


def ensure_fresh(force: bool = False) -> dict:
    """Return a usable cache, refreshing only when stale or forced."""
    cache = load_cache()
    if force or is_stale(cache):
        if not API_KEY:
            print("  WARNING: ODDSPAPI_API_KEY missing — using cache as-is.")
            return cache
        return refresh()

    age = cache_age_days(cache)
    print(f"  Freeze team cache fresh ({age:.1f} days old, "
          f"{len(cache['participants'])} teams). No requests used.")
    return cache


def name_for(participant_id, cache: dict):
    """Team name for a participant ID, or None if not cached."""
    if participant_id is None or not cache:
        return None
    return cache.get("participants", {}).get(str(participant_id))


def main() -> None:
    parser = argparse.ArgumentParser(description="Freeze bot team-name cache")
    parser.add_argument("--force", action="store_true",
                        help="refresh even if the cache is fresh")
    parser.add_argument("--status", action="store_true",
                        help="report cache state without any requests")
    parser.add_argument("--show", type=int, default=0,
                        help="print this many cached team names")
    args = parser.parse_args()

    print("=" * 70)
    print("FREEZE TEAM CACHE")
    print("=" * 70)

    if args.status:
        cache = load_cache()
        age = cache_age_days(cache)
        print(f"  Path:    {CACHE_PATH}")
        print(f"  Teams:   {len(cache.get('participants', {})):,}")
        print(f"  Age:     {'never refreshed' if age is None else f'{age:.1f} days'}")
        print(f"  Stale:   {is_stale(cache)}")
        print("  Requests used: 0")
        return

    cache = ensure_fresh(force=args.force)

    if args.show:
        items = sorted(cache.get("participants", {}).items(),
                       key=lambda kv: kv[1])
        print()
        for participant_id, name in items[:args.show]:
            print(f"  {participant_id:<10} {name}")

    print()
    print("=" * 70)
    print(f"  Total teams cached: {len(cache.get('participants', {})):,}")
    print(f"  Cache file:         {CACHE_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()