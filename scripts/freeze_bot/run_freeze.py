# scripts/freeze_bot/run_freeze.py
"""
Sky Bet Acca Freeze screener.

Finds teams priced MIN_MATCH_ODDS or longer to win in a freeze-eligible
competition, compares that against the same team's First Team To Score
price, flags the ones clearing the ratio threshold, and writes a formatted
Excel workbook.

Match odds come from Paddy Power as a PROXY for Sky Bet (Sky Bet is not in
the OddsPapi feed). FTTS comes from the same call, market 10216.

Team names resolve from the freeze-scoped cache (freeze_teams.py), falling
back to teams.py's 2up_bot cache if needed.

Usage:
    # Inspect payload shape — zero requests
    python scripts/freeze_bot/run_freeze.py --keys data/raw/freeze_probe_nofilter.json

    # Dry run against a saved payload — zero requests
    python scripts/freeze_bot/run_freeze.py --offline data/raw/freeze_probe_nofilter.json

    # Live run — 8 requests, plus up to 2 if the team cache is stale
    python scripts/freeze_bot/run_freeze.py

    # Live run, CSV only
    python scripts/freeze_bot/run_freeze.py --no-excel
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(PROJECT_ROOT / ".env")

import config_freeze as cfg  # noqa: E402

# Primary source: the freeze-scoped cache covering all 36 leagues.
try:
    import freeze_teams
    FREEZE_TEAMS_AVAILABLE = True
except ImportError as _err:
    FREEZE_TEAMS_AVAILABLE = False
    _FREEZE_TEAMS_ERROR = str(_err)

# Fallback: 2up_bot's cache. Covers ~7 leagues, but better than nothing.
try:
    from teams import load_cache as load_2up_cache, name_for as name_for_2up
    TEAMS_FALLBACK_AVAILABLE = True
except ImportError:
    TEAMS_FALLBACK_AVAILABLE = False

# Excel writer. Imported rather than chained in the .bat so the exact CSV
# path is handed over, not re-derived.
try:
    import build_freeze_sheet
    EXCEL_AVAILABLE = True
except ImportError as _err:
    EXCEL_AVAILABLE = False
    _EXCEL_ERROR = str(_err)

API_KEY = os.getenv("ODDSPAPI_API_KEY")

KEYS_FIXTURE_ID = ("fixtureId", "id", "eventId")
KEYS_TOURNAMENT = ("tournamentId", "tournament", "competitionId")
KEYS_START = ("startTime", "startDate", "commenceTime", "kickoff",
              "startTimestamp", "date")


def pick(record: dict, keys, default=""):
    """Return the first usable value among several possible key spellings."""
    for key in keys:
        value = record.get(key)
        if value in (None, ""):
            continue
        if isinstance(value, dict):
            for inner in ("name", "teamName", "tournamentName", "title"):
                if value.get(inner):
                    return value[inner]
            continue
        if isinstance(value, list):
            continue
        return value
    return default


def find_fixtures(payload) -> list:
    """Flatten either payload shape into a list of fixture records."""
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


def markets_of(record: dict) -> dict:
    """Pull the markets dict from either payload shape."""
    if isinstance(record.get("markets"), dict):
        return record["markets"]
    books = record.get("bookmakerOdds", {}) or {}
    for book_data in books.values():
        markets = (book_data or {}).get("markets", {}) or {}
        if markets:
            return markets
    return {}


def price_of(markets: dict, market_id: str, outcome_id: str):
    """Read one decimal price, or None if absent."""
    market = markets.get(market_id)
    if not isinstance(market, dict):
        return None
    outcome = (market.get("outcomes", {}) or {}).get(outcome_id)
    if not isinstance(outcome, dict):
        return None
    player = (outcome.get("players", {}) or {}).get("0", {}) or {}
    try:
        price = float(player.get("price"))
    except (TypeError, ValueError):
        return None
    return price if price > 1.001 else None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class TeamResolver:
    """
    Resolves participant IDs to names, freeze cache first, 2up_bot second.

    Like a VLOOKUP with a second lookup table behind the first: try the wide
    sheet, and only if that misses, try the narrow one.
    """

    def __init__(self, freeze_cache, fallback_cache):
        self.freeze_cache = freeze_cache
        self.fallback_cache = fallback_cache
        self.hits_freeze = 0
        self.hits_fallback = 0
        self.misses = 0

    def name(self, participant_id):
        if participant_id is None:
            self.misses += 1
            return "?"

        if self.freeze_cache and FREEZE_TEAMS_AVAILABLE:
            found = freeze_teams.name_for(participant_id, self.freeze_cache)
            if found:
                self.hits_freeze += 1
                return found

        if self.fallback_cache and TEAMS_FALLBACK_AVAILABLE:
            found = name_for_2up(participant_id, self.fallback_cache)
            if found:
                self.hits_fallback += 1
                return found

        self.misses += 1
        return "?"

    def summary(self) -> str:
        return (f"freeze cache {self.hits_freeze}, "
                f"2up fallback {self.hits_fallback}, "
                f"unresolved {self.misses}")


def build_resolver(offline: bool) -> TeamResolver:
    """Load both caches. Offline mode never refreshes, so it cannot spend."""
    freeze_cache = None
    fallback_cache = None

    if FREEZE_TEAMS_AVAILABLE:
        try:
            if offline:
                freeze_cache = freeze_teams.load_cache()
            else:
                freeze_cache = freeze_teams.ensure_fresh()
            count = len(freeze_cache.get("participants", {}))
            print(f"  Freeze team cache: {count:,} teams")
            if count == 0:
                print("    Build it first:  venv\\Scripts\\python.exe "
                      "scripts\\freeze_bot\\freeze_teams.py --force")
        except Exception as error:  # noqa: BLE001
            print(f"  WARNING: freeze cache unavailable ({error})")
    else:
        print(f"  WARNING: freeze_teams.py not importable ({_FREEZE_TEAMS_ERROR})")

    if TEAMS_FALLBACK_AVAILABLE:
        try:
            fallback_cache = load_2up_cache()
            print(f"  Fallback (2up) cache: "
                  f"{len(fallback_cache.get('participants', {})):,} teams")
        except Exception:  # noqa: BLE001
            fallback_cache = None

    return TeamResolver(freeze_cache, fallback_cache)


def call_api(tournament_ids: list) -> dict | None:
    url = f"{cfg.ODDSPAPI_BASE_URL}/odds-by-tournaments"
    params = {
        "apiKey": API_KEY,
        "tournamentIds": ",".join(str(t) for t in tournament_ids),
        "bookmaker": cfg.MATCH_ODDS_BOOKMAKER,
    }
    try:
        response = requests.get(url, params=params, timeout=90)
    except requests.RequestException as error:
        print(f"    NETWORK ERROR: {error}")
        return None

    if response.status_code == 404:
        print("    No fixtures (tournament out of season) — skipping")
        return None
    if response.status_code != 200:
        print(f"    HTTP {response.status_code}: {response.text[:200]}")
        return None

    print(f"    HTTP 200  ({len(response.content):,} bytes)")
    try:
        return response.json()
    except ValueError:
        print("    ERROR: response was not valid JSON")
        return None


def evaluate(record: dict, resolver: TeamResolver) -> list:
    """
    Return zero or one candidate row for this fixture.

    Only a side priced at or above MIN_MATCH_ODDS is considered. Both sides
    cannot qualify — the draw price would have to be impossibly short — so
    this yields at most one row per match. Draws are never evaluated; you
    cannot freeze a draw.

    participant1Id is the HOME side (confirmed 18 Aug 2026).
    """
    markets = markets_of(record)
    if not markets:
        return []

    home_id = record.get("participant1Id")
    away_id = record.get("participant2Id")
    home_name = resolver.name(home_id)
    away_name = resolver.name(away_id)

    sides = [
        ("home", home_name, away_name, home_id,
         cfg.OUTCOME_MATCH_HOME, cfg.OUTCOME_FTTS_HOME),
        ("away", away_name, home_name, away_id,
         cfg.OUTCOME_MATCH_AWAY, cfg.OUTCOME_FTTS_AWAY),
    ]

    rows = []
    for side, team, opponent, participant_id, match_outcome, ftts_outcome in sides:
        match_odds = price_of(markets, cfg.MARKET_MATCH_ODDS, match_outcome)
        if match_odds is None or match_odds < cfg.MIN_MATCH_ODDS:
            continue

        ftts_odds = price_of(markets, cfg.MARKET_FTTS, ftts_outcome)

        if ftts_odds:
            ratio = match_odds / ftts_odds
            pct_diff = (match_odds - ftts_odds) / ftts_odds * 100
            p_ftts = 1 / ftts_odds
            passes_ratio = ratio >= cfg.MIN_RATIO
            passes_floor = p_ftts >= cfg.P_FTTS_FLOOR
            verdict = "PASS" if (passes_ratio and passes_floor) else "fail"
            if not passes_ratio and not passes_floor:
                reason = "ratio + floor"
            elif not passes_ratio:
                reason = "ratio"
            elif not passes_floor:
                reason = "floor"
            else:
                reason = ""
        else:
            ratio = pct_diff = p_ftts = None
            verdict = "no FTTS"
            reason = "market absent"

        rows.append({
            "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "tournament_id": pick(record, KEYS_TOURNAMENT),
            "tournament": cfg.FREEZE_TOURNAMENTS.get(
                _as_int(pick(record, KEYS_TOURNAMENT)), ""),
            "fixture_id": pick(record, KEYS_FIXTURE_ID),
            "kickoff": pick(record, KEYS_START),
            "side": side,
            "team": team,
            "opponent": opponent,
            "participant_id": participant_id,
            "match_odds_proxy": round(match_odds, 2),
            "ftts_odds": round(ftts_odds, 2) if ftts_odds else "",
            "ratio": round(ratio, 3) if ratio else "",
            "pct_diff": round(pct_diff, 1) if pct_diff else "",
            "p_win_proxy": round(1 / match_odds, 4),
            "p_ftts": round(p_ftts, 4) if p_ftts else "",
            "verdict": verdict,
            "fail_reason": reason,
        })

    return rows


def dump_keys(path: str) -> None:
    """Print the structure of one fixture record so field names can be fixed."""
    with open(path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    fixtures = find_fixtures(payload)
    print(f"Fixture records found: {len(fixtures)}\n")
    if not fixtures:
        print(f"Top-level type: {type(payload).__name__}")
        if isinstance(payload, dict):
            print(f"Top-level keys: {list(payload.keys())}")
        return

    record = fixtures[0]
    print("KEYS ON ONE FIXTURE RECORD")
    print("-" * 60)
    for key, value in record.items():
        kind = type(value).__name__
        if isinstance(value, (dict, list)):
            preview = f"<{kind}, {len(value)} entries>"
        else:
            preview = repr(value)[:70]
        print(f"  {key:<26}{kind:<8}{preview}")

    markets = markets_of(record)
    print(f"\nMarkets on this fixture: {len(markets)}")
    for market_id in (cfg.MARKET_MATCH_ODDS, cfg.MARKET_FTTS):
        present = "PRESENT" if market_id in markets else "ABSENT"
        print(f"  Market {market_id}: {present}")
        if market_id in markets:
            outcomes = markets[market_id].get("outcomes", {})
            for outcome_id in sorted(outcomes.keys()):
                player = (outcomes[outcome_id].get("players", {}) or {}).get("0", {})
                print(f"      outcome {outcome_id}: {player.get('price')}")


def write_outputs(rows: list) -> Path:
    fields = list(rows[0].keys())

    out_dir = PROJECT_ROOT / cfg.OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"freeze_candidates_{stamp}.csv"

    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    log_path = PROJECT_ROOT / cfg.SIGNAL_LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)

    return out_path


def report(rows: list) -> None:
    passing = [r for r in rows if r["verdict"] == "PASS"]
    passing.sort(key=lambda r: -(r["ratio"] or 0))

    print()
    print("=" * 104)
    print(f"CANDIDATES CLEARING BOTH GATES  (ratio >= {cfg.MIN_RATIO}, "
          f"p_ftts >= {cfg.P_FTTS_FLOOR})")
    print("=" * 104)

    if not passing:
        print("  None. Every scanned selection is in the CSV with a fail_reason.")
        return

    print(f"  {'Team':<26}{'vs':<26}{'Match':<8}{'FTTS':<8}"
          f"{'Ratio':<8}{'Diff':<9}League")
    print("  " + "-" * 100)
    for row in passing:
        print(f"  {str(row['team'])[:24]:<26}{str(row['opponent'])[:24]:<26}"
              f"{row['match_odds_proxy']:<8}{row['ftts_odds']:<8}"
              f"{row['ratio']:<8}{str(row['pct_diff']) + '%':<9}"
              f"{row['tournament'][:22]}")


def main() -> None:
    args = sys.argv[1:]

    if "--keys" in args:
        dump_keys(args[args.index("--keys") + 1])
        return

    offline_path = None
    if "--offline" in args:
        offline_path = args[args.index("--offline") + 1]
    make_excel = "--no-excel" not in args

    print("=" * 104)
    print("ACCA FREEZE SCREENER")
    print(f"  Min match odds: {cfg.MIN_MATCH_ODDS}   Min ratio: {cfg.MIN_RATIO}   "
          f"p_ftts floor: {cfg.P_FTTS_FLOOR}")
    print(f"  Match odds via {cfg.MATCH_ODDS_BOOKMAKER} (PROXY for Sky Bet)")
    print("=" * 104)

    resolver = build_resolver(offline=bool(offline_path))

    payloads = []
    requests_used = 0

    if offline_path:
        print(f"\nOFFLINE MODE — reading {offline_path}, zero requests\n")
        with open(offline_path, "r", encoding="utf-8") as handle:
            payloads.append(json.load(handle))
    else:
        if not API_KEY:
            sys.exit(f"ERROR: ODDSPAPI_API_KEY not found in {PROJECT_ROOT / '.env'}")

        ids = list(cfg.FREEZE_TOURNAMENTS.keys())
        batches = [ids[i:i + cfg.TOURNAMENTS_PER_REQUEST]
                   for i in range(0, len(ids), cfg.TOURNAMENTS_PER_REQUEST)]
        print(f"\n{len(ids)} tournaments in {len(batches)} batches "
              f"= {len(batches)} requests\n")

        for index, batch in enumerate(batches, start=1):
            names = ", ".join(cfg.FREEZE_TOURNAMENTS[t][:16] for t in batch)
            print(f"  [{index}/{len(batches)}] {names}")
            payload = call_api(batch)
            requests_used += 1
            if payload:
                payloads.append(payload)
            if index < len(batches):
                time.sleep(cfg.REQUEST_DELAY)

    fixtures = []
    for payload in payloads:
        fixtures.extend(find_fixtures(payload))

    print(f"\nFixtures parsed: {len(fixtures)}")

    rows = []
    for record in fixtures:
        rows.extend(evaluate(record, resolver))

    print(f"Selections at {cfg.MIN_MATCH_ODDS}+ : {len(rows)}")
    print(f"Name lookups: {resolver.summary()}")

    if not rows:
        print("\nNo selections met the minimum price. Nothing written.")
        return

    unknown = sum(1 for r in rows if r["team"] == "?")
    if unknown:
        print(f"\nNOTE: {unknown} of {len(rows)} rows have unnamed teams "
              "(participant IDs are still in the CSV).")

    report(rows)
    out_path = write_outputs(rows)

    xlsx_path = None
    if make_excel:
        if EXCEL_AVAILABLE:
            print()
            try:
                xlsx_path = build_freeze_sheet.build(out_path)
            except Exception as error:  # noqa: BLE001
                # The CSV is already safe on disk, so a failure here costs
                # nothing but the formatting — never the run's 8 requests.
                print(f"  WARNING: Excel build failed ({error})")
                print(f"  Rebuild for free: venv\\Scripts\\python.exe "
                      f"scripts\\freeze_bot\\build_freeze_sheet.py "
                      f"{out_path.relative_to(PROJECT_ROOT)}")
        else:
            print(f"\n  WARNING: build_freeze_sheet.py not importable "
                  f"({_EXCEL_ERROR}) — CSV only.")

    print()
    print("=" * 104)
    print(f"  Rows written:  {len(rows)}")
    print(f"  Candidates:    {out_path}")
    if xlsx_path:
        print(f"  Workbook:      {xlsx_path}")
    print(f"  Signal log:    {PROJECT_ROOT / cfg.SIGNAL_LOG}")
    print(f"  Requests used: {requests_used} (screener)")
    print("=" * 104)


if __name__ == "__main__":
    main()