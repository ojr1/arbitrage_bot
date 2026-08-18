# teams.py
# Team-name cache for 2upbotv2.
#
# WHY THIS EXISTS
# ------------------------------------------------------------------
# Odds responses carry participant1Id and participant2Id but no names, so
# names need a separate /fixtures call. v1 makes that call on EVERY run,
# spending 2-3 requests re-fetching information that has not changed.
#
# WHY THE CACHE IS KEYED ON PARTICIPANT ID, NOT FIXTURE ID
# Fixture IDs churn weekly as matches come and go. Participant IDs do not -
# a club keeps the same ID season after season. Caching participantId -> name
# means every future fixture resolves from IDs the odds response already
# contains, with no API call at all.
#
# COST: 3 requests per refresh, refreshed weekly. Zero on every other run.
#
# /fixtures accepts sportId with from/to dates provided the range is under 10
# days, which returns every league at once - far cheaper than one call per
# tournament, which would be 8 requests.

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from config_v2 import (
    ODDSPAPI_BASE_URL,
    ODDSPAPI_AUTH_PARAM,
    ODDSPAPI_KEY_ENV_VAR,
    REQUEST_DELAY,
    SPORT_ID_SOCCER,
    FIXTURES_MAX_DATE_RANGE_DAYS,
    FIXTURE_WINDOW_DAYS,
    TOURNAMENT_IDS,
    TEAM_CACHE_PATH,
    TEAM_CACHE_REFRESH_DAYS,
)

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_PATH = PROJECT_ROOT / TEAM_CACHE_PATH

load_dotenv(PROJECT_ROOT / ".env")


# ─────────────────────────────────────────────
# API CALL
# ─────────────────────────────────────────────

def call_oddspapi(endpoint, params, api_key, max_retries=2):
    """
    Call an OddsPapi endpoint, pausing first to respect the rate limit.

    On HTTP 429 the API tells us how long to wait in a 'retryMs' field.

    Always prints the response body on failure - the API explains itself
    properly, and throwing that away turns a two-second fix into a guess.
    """
    url = f"{ODDSPAPI_BASE_URL}/{endpoint}"
    query = {ODDSPAPI_AUTH_PARAM: api_key, **params}

    for attempt in range(max_retries + 1):
        time.sleep(REQUEST_DELAY)

        try:
            response = requests.get(url, params=query, timeout=30)
        except requests.RequestException as exc:
            print(f"  {endpoint} failed: {exc}")
            return None

        if response.status_code == 429:
            wait_ms = 2000
            try:
                wait_ms = response.json()["error"].get("retryMs", 2000)
            except Exception:
                pass
            if attempt < max_retries:
                print(f"  Rate limited, waiting {wait_ms}ms")
                time.sleep((wait_ms / 1000) + 0.5)
                continue
            print(f"  Rate limited on {endpoint} - retries exhausted")
            return None

        if response.status_code != 200:
            print(f"  {endpoint} returned HTTP {response.status_code}")
            print(f"    {response.text[:300]}")
            return None

        try:
            return response.json()
        except ValueError as exc:
            print(f"  {endpoint} returned unparseable JSON: {exc}")
            return None

    return None


# ─────────────────────────────────────────────
# CACHE FILE
# ─────────────────────────────────────────────

def empty_cache():
    """The shape of a fresh, unpopulated cache."""
    return {
        "updated": None,
        "participants": {},   # participantId (as string) -> team name
        "source": "oddspapi /fixtures participant1Name / participant2Name",
    }


def load_cache():
    """Read the cache from disk, returning an empty one if absent or broken."""
    if not CACHE_PATH.exists():
        return empty_cache()

    try:
        with CACHE_PATH.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"WARNING: could not read {CACHE_PATH}: {exc}")
        print("         Treating the cache as empty.")
        return empty_cache()

    if not isinstance(data, dict) or "participants" not in data:
        print(f"WARNING: {CACHE_PATH} has an unexpected shape. Rebuilding.")
        return empty_cache()

    return data


def save_cache(cache):
    """Write the cache to disk, creating the folder if needed."""
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(cache, handle, indent=2, sort_keys=True, ensure_ascii=False)


def cache_age_days(cache):
    """How many days since the last refresh, or None if never refreshed."""
    stamp = cache.get("updated")
    if not stamp:
        return None
    try:
        updated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    delta = datetime.now(timezone.utc) - updated
    return delta.total_seconds() / 86400.0


def is_stale(cache, max_age_days=TEAM_CACHE_REFRESH_DAYS):
    """True if the cache is missing, empty, or older than the refresh window."""
    if not cache.get("participants"):
        return True
    age = cache_age_days(cache)
    if age is None:
        return True
    return age >= max_age_days


# ─────────────────────────────────────────────
# REFRESH
# ─────────────────────────────────────────────

def date_chunks(window_days, chunk_days):
    """
    Split the fixture window into date ranges the API will accept.

    /fixtures rejects a from/to span of 10 days or more when only sportId is
    given, so a 21-day window becomes three 9-day chunks.
    """
    chunks = []
    start = datetime.now(timezone.utc)
    end_of_window = start + timedelta(days=window_days)

    while start < end_of_window:
        finish = min(start + timedelta(days=chunk_days), end_of_window)
        chunks.append((start, finish))
        start = finish

    return chunks


def extract_participants(fixtures, wanted_tournaments):
    """
    Pull participantId -> name pairs out of a /fixtures response.

    Only fixtures in our leagues are kept. Using .get() rather than direct
    indexing because a record missing a name should be skipped, not crash
    the run - core.py indexes these directly and would raise a KeyError.
    """
    found = {}
    skipped = 0

    if isinstance(fixtures, dict):
        fixtures = (fixtures.get("data")
                    or fixtures.get("fixtures")
                    or fixtures.get("results")
                    or [])

    if not isinstance(fixtures, list):
        return found, 0

    for fixture in fixtures:
        if not isinstance(fixture, dict):
            continue

        if fixture.get("tournamentId") not in wanted_tournaments:
            continue

        pairs = [
            (fixture.get("participant1Id"), fixture.get("participant1Name")),
            (fixture.get("participant2Id"), fixture.get("participant2Name")),
        ]

        for participant_id, name in pairs:
            if participant_id is None or not name:
                skipped += 1
                continue
            found[str(participant_id)] = name

    return found, skipped


def refresh(api_key, window_days=FIXTURE_WINDOW_DAYS):
    """
    Fetch team names across all leagues and merge them into the cache.

    Merges rather than replaces: a club whose league is between seasons will
    not appear in the current window, and losing its name would break every
    fixture referencing it later.
    """
    cache = load_cache()
    before = len(cache.get("participants", {}))
    wanted = set(TOURNAMENT_IDS)

    chunks = date_chunks(window_days, FIXTURES_MAX_DATE_RANGE_DAYS)
    print(f"Refreshing team names across {len(wanted)} leagues "
          f"in {len(chunks)} date chunks...")

    requests_used = 0
    total_skipped = 0

    for index, (start, finish) in enumerate(chunks, start=1):
        params = {
            "sportId": SPORT_ID_SOCCER,
            "from": start.strftime("%Y-%m-%d"),
            "to": finish.strftime("%Y-%m-%d"),
        }
        print(f"  [{index}/{len(chunks)}] {params['from']} to {params['to']}")

        payload = call_oddspapi("fixtures", params, api_key)
        requests_used += 1

        if payload is None:
            print("      no data returned for this chunk")
            continue

        found, skipped = extract_participants(payload, wanted)
        total_skipped += skipped
        cache["participants"].update(found)
        print(f"      {len(found)} teams in our leagues")

    cache["updated"] = datetime.now(timezone.utc).isoformat()
    save_cache(cache)

    after = len(cache["participants"])
    print(f"\nCache: {before} -> {after} teams "
          f"({after - before} new), {requests_used} requests used")
    if total_skipped:
        print(f"Skipped {total_skipped} entries missing an ID or name.")

    return cache


def ensure_fresh(api_key=None, force=False):
    """
    Return a usable cache, refreshing only if stale.

    This is what the bot calls. On most runs it reads the file and spends
    nothing.
    """
    cache = load_cache()

    if not force and not is_stale(cache):
        age = cache_age_days(cache)
        print(f"Team cache is fresh ({age:.1f} days old, "
              f"{len(cache['participants'])} teams). No requests used.")
        return cache

    if api_key is None:
        api_key = os.getenv(ODDSPAPI_KEY_ENV_VAR)

    if not api_key:
        print(f"ERROR: {ODDSPAPI_KEY_ENV_VAR} not found in .env")
        print("       Cannot refresh. Returning the cache as-is.")
        return cache

    return refresh(api_key)


# ─────────────────────────────────────────────
# LOOKUP
# ─────────────────────────────────────────────

def name_for(participant_id, cache):
    """Team name for a participant ID, or None if not cached."""
    if participant_id is None:
        return None
    return cache.get("participants", {}).get(str(participant_id))


def fixture_teams(fixture, cache):
    """
    Return (home_name, away_name) for an odds record, or (None, None).

    Returns None rather than a placeholder when a name is missing. A fixture
    with an unknown team must be rejected, not matched on a guess.
    """
    if not isinstance(fixture, dict):
        return None, None
    home = name_for(fixture.get("participant1Id"), cache)
    away = name_for(fixture.get("participant2Id"), cache)
    return home, away


# ─────────────────────────────────────────────
# COMMAND LINE
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Inspect or refresh the 2upbotv2 team-name cache."
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Force a refresh even if the cache is fresh. "
                             "Costs 3 OddsPapi requests.")
    parser.add_argument("--status", action="store_true",
                        help="Show cache status without any API call.")
    parser.add_argument("--show", type=int, default=0,
                        help="Print this many cached team names.")
    args = parser.parse_args()

    print("=" * 70)
    print("2upbotv2 - TEAM NAME CACHE")
    print("=" * 70)
    print(f"Cache file: {CACHE_PATH}")

    if args.status:
        cache = load_cache()
        age = cache_age_days(cache)
        age_text = f"{age:.1f} days" if age is not None else "never refreshed"
        print(f"  Teams cached: {len(cache.get('participants', {}))}")
        print(f"  Last refresh: {age_text}")
        print(f"  Stale:        {is_stale(cache)}")
        print("\n" + "=" * 70)
        print("STATUS ONLY - 0 API requests used")
        print("=" * 70)
        return

    cache = ensure_fresh(force=args.refresh)

    if args.show:
        items = sorted(cache.get("participants", {}).items(),
                       key=lambda pair: pair[1])
        print(f"\nFirst {min(args.show, len(items))} teams:")
        for participant_id, name in items[:args.show]:
            print(f"  {participant_id:<10} {name}")

    total = len(cache.get("participants", {}))
    print("\n" + "=" * 70)
    if total:
        print(f"TEAM CACHE READY - {total} teams")
    else:
        print("TEAM CACHE EMPTY - refresh failed or returned nothing")
    print("=" * 70)

    if not total:
        sys.exit(1)


if __name__ == "__main__":
    main()