# team_names.py
# Team-name normalisation, aliasing and matching for 2upbotv2.
#
# WHY THIS MODULE EXISTS
# ------------------------------------------------------------------
# v1 got both the back price and the lay price from OddsPapi, which hands over
# a shared fixtureId guaranteeing they refer to the same match. v2 takes lay
# prices from Betfair directly, and Betfair has no idea what an OddsPapi
# fixtureId is. Fixtures must therefore be matched on team names across two
# sources that spell them differently: "Man Utd" against "Manchester United".
#
# A MISMATCH IS THE WORST POSSIBLE FAILURE. It pairs one team's back price
# with another team's lay price and produces a beautiful fake arbitrage that
# looks exactly like a real one. An unmatched fixture costs one missed signal.
# A mismatched fixture costs real money.
#
# The rule is therefore: EXACT MATCH OR REJECT. No fuzzy scoring anywhere.
#
# Makes no API calls. Pure string handling plus a local JSON cache.

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# =============================================================
# NOISE - safe to remove
# =============================================================
# DELIBERATELY SHORT. Only club-type abbreviations that are noise in every
# context appear here.
#
# Removed after a live test failure 16 Aug 2026: 'sg' turned "Paris SG" into
# "paris" and broke the match. Also removed 'ac', 'as', 'us', 'ss',
# 'borussia', 'athletic', 'atletico', 'club', 'calcio'.
#
# The rule: if stripping a token could ever change WHICH club is meant, it
# does not belong here. Handle those with an explicit alias instead, because
# an alias is visible and reviewable while token-stripping is silent.

CLUB_TOKENS = {
    "fc", "afc", "cf", "sc",
    "sv", "tsv", "vfl", "vfb", "fsv", "bsc",
}

# Punctuation and connectors that vary between feeds.
PUNCTUATION = re.compile(r"[.,'\u2019\-_/&()]+")

# Pure-number tokens: founding years and league prefixes that one feed
# includes and the other does not.
#   "1. FC Cologne" -> "cologne"      (Betfair says "FC Koln")
#   "SV 07 Elversberg" -> "elversberg"
#   "Como 1907" -> "como"
# Checked against all 152 cached club names: no two differ only by a number,
# so this cannot merge two different clubs.
NUMERIC_TOKEN = re.compile(r"^\d+$")

# =============================================================
# QUALIFIERS - NEVER safe to remove
# =============================================================
# These look like noise and are the exact opposite. Strip "Women" and
# "Arsenal Women" collapses into "Arsenal", so a women's fixture gets paired
# with a men's one. They are extracted and compared separately, and BOTH
# SIDES MUST AGREE.

QUALIFIER_TOKENS = {
    "women", "womens", "ladies", "feminine", "femenino", "feminino", "frauen",
    "u21", "u23", "u19", "u18", "youth", "juniors", "junior",
    "ii", "b", "reserves", "reserve", "amateure",
}

# Words that mark a simulated or virtual competition. Any appearance means
# reject outright - these mimic real fixtures and must never be priced.
FAKE_TOKENS = {
    "simulated", "virtual", "esoccer", "esports", "srl", "cyber",
}

# =============================================================
# SEED ALIASES
# =============================================================
# Maps a normalised variant to a canonical normalised name.
#
# TARGETS ARE THE ODDSPAPI CANONICAL FORM, taken from the 152 real club names
# in data/teams.json. Earlier versions pointed at intermediate spellings and
# only worked because canonical() resolves twice. One hop is safer.
#
# ############################################################
# THE PARIS RULE - never alias bare "paris" to anything.
# OddsPapi carries "Paris FC" (canonical "paris") and "Paris Saint-Germain"
# (canonical "paris saint germain"). Both are in Ligue 1 and both are scanned.
# On 16 Aug 2026 the alias generator proposed "paris st g" -> "paris", which
# would have paired PSG's Betfair market with Paris FC's bet365 price. Every
# Paris variant must therefore be spelled out explicitly below.
# ############################################################
#
# Both sides must already be normalised (lowercase, no punctuation, no
# numerals, club tokens stripped).

SEED_ALIASES = {
    # --- England: Premier League and Championship abbreviations ---
    "man utd": "manchester united",
    "man united": "manchester united",
    "manchester utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "wolverhampton": "wolverhampton wanderers",
    "nottm forest": "nottingham forest",
    "notts forest": "nottingham forest",
    "brighton": "brighton and hove albion",
    "brighton hove albion": "brighton and hove albion",
    "west brom": "west bromwich albion",
    "west bromwich": "west bromwich albion",
    "sheff utd": "sheffield united",
    "sheff united": "sheffield united",
    "sheff wed": "sheffield wednesday",
    "sheffield weds": "sheffield wednesday",
    "leeds": "leeds united",
    "newcastle": "newcastle united",
    "west ham": "west ham united",
    "leicester": "leicester city",
    "norwich": "norwich city",
    "stoke": "stoke city",
    "hull": "hull city",
    "swansea": "swansea city",
    "cardiff": "cardiff city",
    "birmingham": "birmingham city",
    "coventry": "coventry city",
    "luton": "luton town",
    "ipswich": "ipswich town",
    "qpr": "queens park rangers",
    "preston": "preston north end",
    "blackburn": "blackburn rovers",
    "bolton": "bolton wanderers",
    "derby": "derby county",
    "plymouth": "plymouth argyle",
    "oxford": "oxford united",
    "middlesboro": "middlesbrough",
    "peterboro": "peterborough united",
    "peterborough": "peterborough united",
    "peterborough utd": "peterborough united",
    "huddersfield": "huddersfield town",
    "charlton": "charlton athletic",
    "wycombe": "wycombe wanderers",
    "lincoln": "lincoln city",

    # --- Scotland ---
    "hearts": "heart of midlothian",
    "hibs": "hibernian",

    # --- Spain ---
    "ath madrid": "atletico madrid",
    "atl madrid": "atletico madrid",
    "ath bilbao": "athletic bilbao",
    "atletico bilbao": "athletic bilbao",
    "betis": "real betis seville",
    "real betis": "real betis seville",
    "sociedad": "real sociedad san sebastian",
    "real sociedad": "real sociedad san sebastian",
    "celta": "rc celta de vigo",
    "celta vigo": "rc celta de vigo",
    "espanyol": "espanyol barcelona",
    "alaves": "deportivo alaves",
    # RESOLVED BY HAND. Betfair's short name for Deportivo La Coruna. Safe
    # because Betfair lists Alaves separately, in the same dump. If Betfair
    # ever uses "Deportivo" for Alaves this becomes a mismatch - say so and
    # it comes straight back out.
    "deportivo": "rc deportivo de a coruna",
    "deportivo la coruna": "rc deportivo de a coruna",

    # --- Germany ---
    "bayern munchen": "bayern munich",
    "bayern": "bayern munich",
    "dortmund": "borussia dortmund",
    "bvb": "borussia dortmund",
    # RESOLVED BY HAND - Betfair writes "Mgladbach".
    "mgladbach": "borussia monchengladbach",
    "gladbach": "borussia monchengladbach",
    "monchengladbach": "borussia monchengladbach",
    "borussia mgladbach": "borussia monchengladbach",
    # RESOLVED BY HAND - Betfair "FC Koln" against OddsPapi "1. FC Cologne",
    # which the numeric strip reduces to "cologne".
    "koln": "cologne",
    "cologne": "cologne",
    "leverkusen": "bayer leverkusen",
    "frankfurt": "eintracht frankfurt",
    "leipzig": "rb leipzig",
    "hoffenheim": "tsg hoffenheim",
    "elversberg": "elversberg",
    "paderborn": "paderborn",

    # --- Italy ---
    "inter": "inter milano",
    "inter milan": "inter milano",
    "internazionale": "inter milano",
    "milan": "ac milan",
    "juve": "juventus turin",
    "juventus": "juventus turin",
    "roma": "as roma",
    "lazio": "lazio rome",
    "napoli": "ssc napoli",
    "fiorentina": "acf fiorentina",
    "atalanta": "atalanta bc",
    "genoa": "genoa cfc",
    "udinese": "udinese calcio",
    "sassuolo": "sassuolo calcio",
    "parma": "parma calcio",
    "cagliari": "cagliari calcio",
    "frosinone": "frosinone calcio",
    "lecce": "us lecce",
    "como": "como",

    # --- France ---
    # See THE PARIS RULE above. Every variant is explicit; none maps to
    # bare "paris", which is Paris FC.
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "paris st g": "paris saint germain",
    "paris st germain": "paris saint germain",
    "paris saint germain": "paris saint germain",
    "marseille": "olympique marseille",
    "lyon": "olympique lyon",
    "olympique lyonnais": "olympique lyon",
    "nice": "ogc nice",
    "lens": "racing club de lens",
    "lille": "lille osc",
    "auxerre": "aj auxerre",
    "angers": "angers sco",
    "brest": "stade brest",
    "le havre": "le havre ac",
    "strasbourg": "strasbourg alsace",
    # RESOLVED BY HAND - Betfair "Rennes", OddsPapi "Stade Rennais FC".
    "rennes": "stade rennais",
    "stade rennes": "stade rennais",

    # --- Brazil ---
    # State suffixes (RJ, SP, MG, RS, BA, PR, PA) are NEVER stripped: there
    # are Botafogos in RJ, SP and PB, so the suffix is the only thing telling
    # them apart.
    "flamengo": "cr flamengo rj",
    "botafogo fr": "botafogo fr rj",
    "corinthians": "corinthians sp",
    "internacional": "internacional rs",
    "cruzeiro": "cruzeiro ec mg",
    "cruzeiro mg": "cruzeiro ec mg",
    "remo": "clube do remo pa",
    "mirassol": "mirassol sp",
    "atletico mg": "atletico mineiro mg",
    "atletico mineiro": "atletico mineiro mg",
    # RESOLVED BY HAND - Betfair "EC Vitoria Salvador", OddsPapi
    # "EC Vitoria BA". Neither is a subset of the other.
    "ec vitoria salvador": "ec vitoria ba",
    "vitoria salvador": "ec vitoria ba",
}


# =============================================================
# NORMALISATION
# =============================================================


def strip_accents(text):
    """
    Remove accents so 'Atletico' and 'Atlético' compare equal.

    NFKD splits an accented character into a base letter plus a combining
    mark; discarding the marks leaves the plain letter behind.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed
                   if not unicodedata.combining(ch))


def tokenise(name):
    """Lowercase, strip accents and punctuation, split into words."""
    if not isinstance(name, str):
        return []
    text = strip_accents(name).lower()
    text = PUNCTUATION.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text.split()


def extract_qualifiers(tokens):
    """
    Split tokens into (qualifiers, remaining).

    Qualifiers are NEVER discarded - they are compared separately, because
    'Arsenal Women' and 'Arsenal' are different teams.
    """
    qualifiers = set()
    remaining = []
    for token in tokens:
        if token in QUALIFIER_TOKENS:
            qualifiers.add(token)
        else:
            remaining.append(token)
    return qualifiers, remaining


def looks_fake(name):
    """True if the name belongs to a simulated or virtual competition."""
    return bool(set(tokenise(name)) & FAKE_TOKENS)


def normalise(name):
    """
    Reduce a team name to its comparable form, WITHOUT the qualifiers.

    Removes club-type tokens and pure numbers, but only while something is
    left - a name made entirely of such tokens keeps its original form rather
    than becoming an empty string that would match everything.
    """
    tokens = tokenise(name)
    _, tokens = extract_qualifiers(tokens)

    stripped = [
        t for t in tokens
        if t not in CLUB_TOKENS and not NUMERIC_TOKEN.match(t)
    ]
    if not stripped:
        stripped = tokens

    return " ".join(stripped)


# =============================================================
# ALIAS TABLE
# =============================================================


def load_aliases(path):
    """
    Load the alias table, creating it from the seeds if absent.

    Like a mapping sheet in a workbook: one place that says these different
    spellings all mean the same thing.

    NOTE: entries in the file WIN over the seeds, so a hand-made decision
    outranks anything shipped here. If the seeds change and the file is
    stale, delete the file and let it regenerate.
    """
    alias_path = Path(path)
    if alias_path.exists():
        try:
            with alias_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                merged = dict(SEED_ALIASES)
                merged.update(data)
                return merged
        except (json.JSONDecodeError, OSError) as exc:
            print(f"WARNING: could not read {alias_path}: {exc}")
            print("         Falling back to seed aliases only.")
        return dict(SEED_ALIASES)

    alias_path.parent.mkdir(parents=True, exist_ok=True)
    with alias_path.open("w", encoding="utf-8") as handle:
        json.dump(SEED_ALIASES, handle, indent=2, sort_keys=True)
    print(f"Created alias table with {len(SEED_ALIASES)} seeds "
          f"at {alias_path}")
    return dict(SEED_ALIASES)


def canonical(name, aliases):
    """
    Full canonical form: normalise, then resolve through the alias table.

    Applied twice so a chain like 'bvb' -> 'borussia dortmund' resolves even
    if the target is itself an alias key. Two passes is enough for any sane
    table and cannot loop forever.
    """
    key = normalise(name)
    for _ in range(2):
        mapped = aliases.get(key)
        if mapped is None or mapped == key:
            break
        key = mapped
    return key


# =============================================================
# MATCHING
# =============================================================


def teams_match(name_a, name_b, aliases):
    """
    Decide whether two names refer to the same team.

    Returns (matched, reason). The reason is written to the rejection log so
    the alias table can be grown from real evidence.

    EXACT MATCH OR REJECT. No fuzzy scoring in this function.
    """
    if not name_a or not name_b:
        return False, "missing name"

    if looks_fake(name_a) or looks_fake(name_b):
        return False, "simulated or virtual competition"

    quals_a, _ = extract_qualifiers(tokenise(name_a))
    quals_b, _ = extract_qualifiers(tokenise(name_b))

    if quals_a != quals_b:
        return False, (f"qualifier mismatch: {sorted(quals_a) or 'none'} "
                       f"vs {sorted(quals_b) or 'none'}")

    canon_a = canonical(name_a, aliases)
    canon_b = canonical(name_b, aliases)

    if not canon_a or not canon_b:
        return False, "empty after normalisation"

    if canon_a == canon_b:
        return True, "exact"

    return False, f"no alias: '{canon_a}' vs '{canon_b}'"


def fixtures_match(home_a, away_a, home_b, away_b, aliases):
    """
    Both teams must match, in the same order.

    Order matters: a home/away swap between feeds would pair the back price
    on one team with the lay price on the other - exactly the failure this
    module exists to prevent. If a feed ever reverses them, that must be
    fixed at the source, not papered over here.
    """
    home_ok, home_reason = teams_match(home_a, home_b, aliases)
    if not home_ok:
        return False, f"home: {home_reason}"

    away_ok, away_reason = teams_match(away_a, away_b, aliases)
    if not away_ok:
        return False, f"away: {away_reason}"

    return True, "both teams matched"


# =============================================================
# SELF-TEST
# =============================================================


def run_tests():
    """
    Prove the module behaves before anything depends on it.

    The NEGATIVE cases matter more than the positive ones. A matcher that
    says yes too often is far more dangerous than one that says no too often.
    """
    aliases = dict(SEED_ALIASES)
    checks = 0
    failures = []

    def expect_match(a, b):
        nonlocal checks
        checks += 1
        ok, reason = teams_match(a, b, aliases)
        if not ok:
            failures.append(f"SHOULD MATCH: '{a}' vs '{b}' -> {reason}")

    def expect_reject(a, b):
        nonlocal checks
        checks += 1
        ok, reason = teams_match(a, b, aliases)
        if ok:
            failures.append(f"SHOULD REJECT: '{a}' vs '{b}' -> matched")

    # --- should match: England ---
    expect_match("Man Utd", "Manchester United")
    expect_match("Manchester United FC", "Man United")
    expect_match("Arsenal", "Arsenal FC")
    expect_match("Spurs", "Tottenham Hotspur")
    expect_match("Wolves", "Wolverhampton Wanderers")
    expect_match("Nottm Forest", "Nottingham Forest")
    expect_match("Brighton", "Brighton & Hove Albion")
    expect_match("QPR", "Queens Park Rangers")
    expect_match("Sheff Utd", "Sheffield United")
    expect_match("West Brom", "West Bromwich Albion")
    expect_match("Cardiff", "Cardiff City")
    expect_match("Wrexham", "Wrexham AFC")

    # --- should match: Europe, real Betfair vs OddsPapi pairs ---
    expect_match("Atletico Madrid", "Atlético Madrid")
    expect_match("Bayern Munchen", "Bayern Munich")
    expect_match("Strasbourg", "Strasbourg Alsace")
    expect_match("Alaves", "Deportivo Alaves")
    expect_match("Rennes", "Stade Rennais FC")
    expect_match("Mgladbach", "Borussia Monchengladbach")
    expect_match("FC Koln", "1. FC Cologne")
    expect_match("Elversberg", "SV 07 Elversberg")
    expect_match("Paderborn", "SC Paderborn 07")
    expect_match("Como", "Como 1907")
    expect_match("Inter", "Inter Milano")
    expect_match("Juventus", "Juventus Turin")
    expect_match("Napoli", "SSC Napoli")
    expect_match("Lyon", "Olympique Lyon")
    expect_match("Celta Vigo", "RC Celta de Vigo")
    expect_match("Betis", "Real Betis Seville")

    # --- should match: Brazil, state suffixes preserved ---
    expect_match("Flamengo", "CR Flamengo RJ")
    expect_match("Corinthians", "SC Corinthians SP")
    expect_match("Remo", "Clube do Remo PA")
    expect_match("Botafogo FR", "Botafogo FR RJ")
    expect_match("EC Vitoria Salvador", "EC Vitoria BA")

    # --- THE PARIS TRAP - the live near-miss of 16 Aug 2026 ---
    expect_match("Paris St-G", "Paris Saint-Germain")
    expect_match("PSG", "Paris Saint-Germain")
    expect_reject("Paris St-G", "Paris FC")
    expect_reject("Paris FC", "Paris Saint-Germain")

    # --- THE DEPORTIVO TRAP ---
    expect_match("Deportivo", "RC Deportivo De A Coruna")
    expect_reject("Deportivo", "Deportivo Alaves")
    expect_reject("Deportivo Alaves", "RC Deportivo De A Coruna")

    # --- must reject: different clubs, similar names ---
    expect_reject("Manchester United", "Manchester City")
    expect_reject("Sheffield United", "Sheffield Wednesday")
    expect_reject("Real Madrid", "Real Sociedad")
    expect_reject("AC Milan", "Inter Milan")
    expect_reject("Athletic Bilbao", "Atletico Madrid")
    expect_reject("Nottingham Forest", "Norwich City")
    expect_reject("Bristol City", "Bristol Rovers")
    expect_reject("Olympique Lyon", "Olympique Marseille")

    # --- must reject: qualifier mismatches ---
    expect_reject("Arsenal Women", "Arsenal")
    expect_reject("Chelsea", "Chelsea Ladies")
    expect_reject("Barcelona", "Barcelona B")
    expect_reject("Real Madrid", "Real Madrid U21")

    # --- must reject: simulated competitions ---
    expect_reject("Arsenal (SRL)", "Arsenal")
    expect_reject("Liverpool Esports", "Liverpool")

    # --- must reject: empties ---
    expect_reject("", "Arsenal")
    expect_reject("Arsenal", None)

    # --- fixture-level, including the disaster case ---
    checks += 1
    ok, _ = fixtures_match("Man Utd", "Man City",
                           "Manchester United", "Manchester City", aliases)
    if not ok:
        failures.append("SHOULD MATCH: full fixture Man Utd v Man City")

    checks += 1
    ok, reason = fixtures_match("Man Utd", "Man City",
                                "Manchester City", "Manchester United",
                                aliases)
    if ok:
        failures.append("SHOULD REJECT: home/away reversed fixture matched")

    return checks, failures


if __name__ == "__main__":
    print("=" * 70)
    print("team_names.py SELF-TEST (no API requests)")
    print("=" * 70)

    checks, failures = run_tests()

    for failure in failures:
        print(f"  FAIL  {failure}")

    print("")
    print("=" * 70)
    if failures:
        print(f"TESTS FAILED - {len(failures)} of {checks} checks failed")
        print("=" * 70)
        sys.exit(1)

    print(f"TEAM NAME TESTS PASSED - {checks} checks")
    print("=" * 70)