# scripts/2upbotv2/generate_aliases.py
"""
Alias proposal generator for 2upbotv2.

Compares the OddsPapi team names in data/teams.json against the Betfair runner
names in the newest data/raw/betfair_markets_*.json, and proposes aliases for
the pairs that do not already match.

THE SAFETY RULE
A Betfair name is only paired with an OddsPapi name when EXACTLY ONE candidate
fits. Two or more candidates means AMBIGUOUS, and ambiguous entries are
reported for you to decide - never guessed at.

Why that matters, from real data:
  Betfair "Deportivo" is Deportivo La Coruna. OddsPapi carries BOTH
  "RC Deportivo De A Coruna" AND "Deportivo Alaves", both in La Liga. A fuzzy
  matcher would pick one and be wrong about half the time - pairing one club's
  back price with another's lay price. That is the fake-arbitrage failure this
  whole module exists to prevent.

Proposals are written to data/team_aliases_proposed.json for review. Nothing
is written to the live alias table automatically.

Makes NO API requests.
"""

import argparse
import json
import sys
from pathlib import Path

# This script lives in scripts/2upbotv2/, but team_names.py and config_v2.py
# live at the project root. The folder name starts with a digit so it cannot
# be an importable package - the root is added to the import path instead.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from team_names import (  # noqa: E402
    SEED_ALIASES,
    canonical,
    load_aliases,
    normalise,
    tokenise,
    extract_qualifiers,
)
from config_v2 import TEAM_CACHE_PATH, TEAM_ALIAS_PATH  # noqa: E402

RAW_DIR = PROJECT_ROOT / "data" / "raw"
CACHE_PATH = PROJECT_ROOT / TEAM_CACHE_PATH
ALIAS_PATH = PROJECT_ROOT / TEAM_ALIAS_PATH
PROPOSED_PATH = PROJECT_ROOT / "data" / "team_aliases_proposed.json"

# Betfair's name for the draw selection, which is not a team.
DRAW_RUNNER_NAMES = {"the draw", "draw"}


# ─────────────────────────────────────────────
# INPUTS
# ─────────────────────────────────────────────

def newest_betfair_file():
    """Most recently saved Betfair market dump."""
    candidates = sorted(
        RAW_DIR.glob("betfair_markets_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        print(f"ERROR: no betfair_markets_*.json found in {RAW_DIR}")
        print("       Run: python betfair_client.py --markets <ids> --save")
        sys.exit(1)
    return candidates[0]


def load_oddspapi_names():
    """Team names from the participant cache."""
    if not CACHE_PATH.exists():
        print(f"ERROR: {CACHE_PATH} not found.")
        print("       Run: python teams.py --refresh")
        sys.exit(1)

    with CACHE_PATH.open("r", encoding="utf-8") as handle:
        cache = json.load(handle)

    names = sorted(set(cache.get("participants", {}).values()))
    if not names:
        print("ERROR: the team cache is empty.")
        sys.exit(1)
    return names


def load_betfair_names(path):
    """
    Team names from a saved Betfair market dump.

    Returns {name: [competition names it appeared in]} so ambiguous cases can
    show which league a name came from.
    """
    with path.open("r", encoding="utf-8") as handle:
        markets = json.load(handle)

    names = {}
    for market in markets:
        competition = market.get("competition_name") or "?"
        for runner in market.get("runners", []):
            name = runner.get("name")
            if not name:
                continue
            if name.strip().lower() in DRAW_RUNNER_NAMES:
                continue
            names.setdefault(name, set()).add(competition)

    return {name: sorted(comps) for name, comps in sorted(names.items())}


# ─────────────────────────────────────────────
# CANDIDATE FINDING
# ─────────────────────────────────────────────

def token_set(name):
    """Meaningful tokens of a name, qualifiers removed."""
    _, tokens = extract_qualifiers(tokenise(name))
    return set(normalise(" ".join(tokens)).split())


def find_candidates(betfair_name, oddspapi_index):
    """
    OddsPapi names that could be the same club as this Betfair name.

    A candidate is one whose token set CONTAINS the Betfair tokens, or is
    contained by them. Containment in either direction covers both
    "Strasbourg" -> "Strasbourg Alsace" and the reverse.

    Returns a list. One entry means a safe proposal. More than one means
    ambiguous, and nothing is proposed.
    """
    betfair_tokens = token_set(betfair_name)
    if not betfair_tokens:
        return []

    candidates = []
    for oddspapi_name, oddspapi_tokens in oddspapi_index.items():
        if not oddspapi_tokens:
            continue
        if betfair_tokens <= oddspapi_tokens or oddspapi_tokens <= betfair_tokens:
            candidates.append(oddspapi_name)

    return candidates


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Propose team-name aliases from live data. No API calls."
    )
    parser.add_argument("--betfair-file", type=str, default=None,
                        help="Saved Betfair dump. Defaults to the newest.")
    parser.add_argument("--write", action="store_true",
                        help="Merge the UNAMBIGUOUS proposals straight into "
                             "the live alias table. Review first without it.")
    args = parser.parse_args()

    betfair_path = (Path(args.betfair_file) if args.betfair_file
                    else newest_betfair_file())

    print("=" * 70)
    print("2upbotv2 - ALIAS GENERATOR (no API requests)")
    print("=" * 70)
    print(f"OddsPapi cache: {CACHE_PATH}")
    print(f"Betfair dump:   {betfair_path}")

    oddspapi_names = load_oddspapi_names()
    betfair_names = load_betfair_names(betfair_path)
    aliases = load_aliases(ALIAS_PATH)

    print(f"\n  {len(oddspapi_names)} OddsPapi teams")
    print(f"  {len(betfair_names)} Betfair teams in this dump")
    print(f"  {len(aliases)} aliases currently loaded")

    # Canonical form of every OddsPapi name, and its token set.
    oddspapi_canonical = {name: canonical(name, aliases)
                          for name in oddspapi_names}
    canonical_to_names = {}
    for name, canon in oddspapi_canonical.items():
        canonical_to_names.setdefault(canon, []).append(name)

    oddspapi_index = {name: token_set(name) for name in oddspapi_names}

    matched = []
    proposed = {}
    ambiguous = []
    unresolved = []

    for betfair_name, competitions in betfair_names.items():
        betfair_canon = canonical(betfair_name, aliases)

        if betfair_canon in canonical_to_names:
            matched.append((betfair_name,
                            canonical_to_names[betfair_canon][0]))
            continue

        candidates = find_candidates(betfair_name, oddspapi_index)

        # A candidate list that all resolves to ONE canonical form is still
        # a single club - two spellings of the same team, not two teams.
        distinct = sorted({oddspapi_canonical[name] for name in candidates})

        if len(distinct) == 1:
            proposed[betfair_canon] = distinct[0]
        elif len(distinct) > 1:
            ambiguous.append((betfair_name, competitions, candidates))
        else:
            unresolved.append((betfair_name, competitions))

    # ---- Report ---------------------------------------------------------
    print("\n" + "=" * 70)
    print(f"ALREADY MATCHING: {len(matched)}")
    print("=" * 70)
    for betfair_name, oddspapi_name in matched[:15]:
        print(f"  {betfair_name:<30} = {oddspapi_name}")
    if len(matched) > 15:
        print(f"  ... and {len(matched) - 15} more")

    print("\n" + "=" * 70)
    print(f"PROPOSED ALIASES: {len(proposed)}")
    print("=" * 70)
    print("  Exactly one candidate each. Review before accepting.")
    print("")
    for betfair_canon, oddspapi_canon in sorted(proposed.items()):
        print(f"  \"{betfair_canon}\" -> \"{oddspapi_canon}\"")

    print("\n" + "=" * 70)
    print(f"AMBIGUOUS - DECIDE BY HAND: {len(ambiguous)}")
    print("=" * 70)
    print("  More than one club fits. NOTHING has been proposed for these.")
    print("  Getting one wrong pairs two different teams' prices together.")
    print("")
    for betfair_name, competitions, candidates in ambiguous:
        print(f"  Betfair '{betfair_name}'  ({', '.join(competitions)})")
        for candidate in candidates:
            print(f"      could be: {candidate}")

    print("\n" + "=" * 70)
    print(f"UNRESOLVED - NO CANDIDATE FOUND: {len(unresolved)}")
    print("=" * 70)
    print("  Either the club is missing from the team cache, or the two")
    print("  names share no tokens at all (e.g. 'EC Vitoria Salvador'")
    print("  against 'EC Vitoria BA').")
    print("")
    for betfair_name, competitions in unresolved:
        print(f"  {betfair_name:<34} ({', '.join(competitions)})")

    # ---- Save -----------------------------------------------------------
    PROPOSED_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "proposed": proposed,
        "ambiguous": [
            {"betfair": name, "competitions": comps, "candidates": cands}
            for name, comps, cands in ambiguous
        ],
        "unresolved": [
            {"betfair": name, "competitions": comps}
            for name, comps in unresolved
        ],
    }
    PROPOSED_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n  Proposals written to {PROPOSED_PATH}")

    if args.write and proposed:
        existing = {}
        if ALIAS_PATH.exists():
            try:
                with ALIAS_PATH.open("r", encoding="utf-8") as handle:
                    existing = json.load(handle)
            except (json.JSONDecodeError, OSError):
                existing = {}

        before = len(existing)
        # Never overwrite an alias already in the file - a hand-made decision
        # outranks a generated proposal.
        for key, value in proposed.items():
            existing.setdefault(key, value)

        ALIAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        ALIAS_PATH.write_text(
            json.dumps(existing, indent=2, sort_keys=True,
                       ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"  Alias table updated: {before} -> {len(existing)} entries")
    elif proposed:
        print("  Nothing written to the live table. Re-run with --write "
              "to accept the unambiguous proposals.")

    coverage = len(matched) + len(proposed)
    total = len(betfair_names)
    print("\n" + "=" * 70)
    print(f"ALIAS GENERATION COMPLETE - {coverage}/{total} Betfair teams "
          f"resolvable ({len(ambiguous)} ambiguous, "
          f"{len(unresolved)} unresolved)")
    print("0 API requests used")
    print("=" * 70)


if __name__ == "__main__":
    main()