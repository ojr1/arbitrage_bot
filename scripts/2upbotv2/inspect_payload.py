# scripts/2upbotv2/inspect_payload.py
"""
Offline structure inspector for 2upbotv2.

Reads a raw OddsPapi payload already saved to data/raw/ and reports what is
actually inside it. Makes NO API requests - it only reads a local file, so it
can be run as often as you like at zero cost to the monthly quota.

Answers:
  1. What shape is the response? (top-level type, keys, nesting)
  2. Where do bookmaker identifiers live - keys or values?
  3. Where exactly does '2up' appear, and in what context?
"""

import argparse
import json
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# CONFIGURATION
# --------------------------------------------------------------------------

# Project root is two levels up from this file (scripts/2upbotv2/ -> root).
ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"

# How deep to map the structure. Deeper costs more output, not more accuracy.
MAX_DEPTH = 7

# A dictionary with more keys than this is treated as a KEYED COLLECTION -
# i.e. the keys are data (bookmaker names, IDs) rather than field names.
LARGE_DICT_THRESHOLD = 30

# When sampling children of a list or keyed collection, how many to follow.
SAMPLE_CHILDREN = 2

# Terms to locate in the payload, with a plain-English reason for each.
SEARCH_TERMS = {
    "bet365": "primary book - reveals where bookmaker names live",
    "paddy": "target book",
    "mgm": "target book",
    "betfair": "exchange - lay side",
    "2up": "separate early-payout market?",
    "availabletolay": "exchange ladder structure",
}

# Maximum hits to report per search term.
MAX_HITS_PER_TERM = 6

# --------------------------------------------------------------------------
# FILE SELECTION
# --------------------------------------------------------------------------


def newest_raw_file():
    """Return the most recently modified probe payload in data/raw/."""
    candidates = sorted(
        RAW_DIR.glob("probe_bookmakers_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        print(f"ERROR: No probe_bookmakers_*.json found in {RAW_DIR}")
        print("       Run probe_bookmakers.py first.")
        sys.exit(1)
    return candidates[0]


# --------------------------------------------------------------------------
# STRUCTURE MAPPING
# --------------------------------------------------------------------------


def type_name(node):
    """Short readable name for a JSON value's type."""
    if isinstance(node, dict):
        return f"dict({len(node)})"
    if isinstance(node, list):
        return f"list({len(node)})"
    if isinstance(node, bool):
        return "bool"
    if isinstance(node, str):
        return "str"
    if isinstance(node, (int, float)):
        return "number"
    if node is None:
        return "null"
    return "unknown"


def short_sample(node):
    """A truncated preview of a scalar value, for the structure map."""
    if isinstance(node, (str, int, float, bool)):
        text = str(node)
        return text[:60] + ("..." if len(text) > 60 else "")
    return ""


def map_structure(node, path, depth, census, keyed_collections):
    """
    Walk the payload recording every distinct path and what type sits there.

    Recursive means the function calls itself to go one level deeper, the
    same way you drill into nested folders.
    """
    entry = census.setdefault(
        path, {"types": set(), "count": 0, "sample": ""}
    )
    entry["types"].add(type_name(node))
    entry["count"] += 1
    if not entry["sample"]:
        entry["sample"] = short_sample(node)

    if depth >= MAX_DEPTH:
        return

    if isinstance(node, dict):
        keys = list(node.keys())
        if len(keys) > LARGE_DICT_THRESHOLD:
            # The keys here are almost certainly data, not field names.
            keyed_collections.setdefault(
                path, {"key_count": len(keys), "sample_keys": keys[:25]}
            )
            for key in keys[:SAMPLE_CHILDREN]:
                map_structure(node[key], f"{path}/{{key}}", depth + 1,
                              census, keyed_collections)
        else:
            for key in keys:
                map_structure(node[key], f"{path}/{key}", depth + 1,
                              census, keyed_collections)

    elif isinstance(node, list):
        for item in node[:SAMPLE_CHILDREN]:
            map_structure(item, f"{path}[]", depth + 1,
                          census, keyed_collections)


# --------------------------------------------------------------------------
# TERM SEARCH
# --------------------------------------------------------------------------


def search_term(node, path, term, hits, parent):
    """
    Find every place a term appears, as a key or as a string value, and
    record the path plus the object it was found inside.
    """
    if len(hits) >= MAX_HITS_PER_TERM:
        return

    if isinstance(node, dict):
        for key, value in node.items():
            if term in str(key).lower():
                hits.append({
                    "path": f"{path}/{key}",
                    "kind": "KEY",
                    "preview": json.dumps(value)[:200],
                    "parent": node,
                })
                if len(hits) >= MAX_HITS_PER_TERM:
                    return
            search_term(value, f"{path}/{key}", term, hits, node)
            if len(hits) >= MAX_HITS_PER_TERM:
                return

    elif isinstance(node, list):
        for index, item in enumerate(node):
            search_term(item, f"{path}[{index}]", term, hits, parent)
            if len(hits) >= MAX_HITS_PER_TERM:
                return

    elif isinstance(node, str):
        if term in node.lower():
            hits.append({
                "path": path,
                "kind": "VALUE",
                "preview": node[:200],
                "parent": parent,
            })


# --------------------------------------------------------------------------
# MAIN
# --------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Inspect a saved OddsPapi payload. Makes no API requests."
    )
    parser.add_argument("--file", type=str, default=None,
                        help="Path to a saved JSON payload. Defaults to the "
                             "newest probe_bookmakers_*.json in data/raw/.")
    args = parser.parse_args()

    path = Path(args.file) if args.file else newest_raw_file()

    print("=" * 70)
    print("2upbotv2 - OFFLINE PAYLOAD INSPECTOR (no API requests)")
    print("=" * 70)
    print(f"File: {path}")
    print(f"Size: {path.stat().st_size:,} bytes")
    print("\nLoading... (a 14 MB file may take a few seconds)")

    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    print("Loaded.\n")

    # ---- Top level -------------------------------------------------------
    print("=" * 70)
    print("TOP LEVEL")
    print("=" * 70)
    print(f"  Type: {type_name(payload)}")

    if isinstance(payload, dict):
        keys = list(payload.keys())
        print(f"  Keys ({len(keys)}): {keys[:40]}")
        for key in keys[:10]:
            print(f"    {key:<24} -> {type_name(payload[key])}")
    elif isinstance(payload, list) and payload:
        print(f"  Length: {len(payload)}")
        print(f"  First item type: {type_name(payload[0])}")
        if isinstance(payload[0], dict):
            print(f"  First item keys: {list(payload[0].keys())[:40]}")

    # ---- Structure map ---------------------------------------------------
    census = {}
    keyed_collections = {}
    map_structure(payload, "", 0, census, keyed_collections)

    print("\n" + "=" * 70)
    print(f"STRUCTURE MAP ({len(census)} distinct paths)")
    print("=" * 70)
    for route in sorted(census.keys()):
        info = census[route]
        types = ",".join(sorted(info["types"]))
        label = route if route else "(root)"
        line = f"  {label:<52} {types}"
        if info["sample"]:
            line += f"  e.g. {info['sample']}"
        print(line)

    # ---- Keyed collections ----------------------------------------------
    print("\n" + "=" * 70)
    print("KEYED COLLECTIONS (dicts where the KEYS are data)")
    print("=" * 70)
    if keyed_collections:
        for route, info in keyed_collections.items():
            label = route if route else "(root)"
            print(f"\n  Path: {label}")
            print(f"  Key count: {info['key_count']}")
            print(f"  Sample keys: {info['sample_keys']}")
    else:
        print("  None found. Bookmakers are not stored as dictionary keys.")

    # ---- Term search -----------------------------------------------------
    print("\n" + "=" * 70)
    print("TERM SEARCH")
    print("=" * 70)
    for term, reason in SEARCH_TERMS.items():
        hits = []
        search_term(payload, "", term, hits, None)
        print(f"\n--- '{term}'  ({reason})")
        if not hits:
            print("    no occurrences")
            continue
        for hit in hits:
            print(f"    {hit['kind']:<6} {hit['path']}")
            print(f"           {hit['preview']}")
        # Show the containing object for the first hit only.
        first_parent = hits[0].get("parent")
        if isinstance(first_parent, dict):
            print("    -- containing object --")
            print("    " + json.dumps(first_parent, indent=2)[:800]
                  .replace("\n", "\n    "))

    print("\n" + "=" * 70)
    print("INSPECTION COMPLETE - 0 API requests used")
    print("=" * 70)


if __name__ == "__main__":
    main()