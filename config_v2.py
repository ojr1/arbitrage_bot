# config_v2.py
# Constants for 2upbotv2. Standalone by design.
#
# WHY THIS FILE DUPLICATES config.py RATHER THAN IMPORTING IT
# ------------------------------------------------------------------
# v1 must stay untouched so the two bots can be run side by side and their
# outputs compared. If v2 imported v1's constants, tuning v2 would silently
# change v1 and the comparison would be worthless. The duplication is the
# price of that isolation and is intentional.
#
# CONFLICTS WITH config.py, DECLARED:
#   1. Leagues: 8 here, 10 in v1. League One (24) and League Two (25) removed -
#      neither returned odds from any bookmaker across two consecutive runs.
#   2. Books: three back books here, one in v1.
#   3. Currency: exchange sizes labelled GBP here. v1 labelled them "$", which
#      was wrong - Betfair reports in the account currency.
#
# Nothing in this file computes anything. It is the settings sheet.

# =============================================================
# ODDSPAPI CONNECTION
# =============================================================

ODDSPAPI_BASE_URL = "https://api.oddspapi.io/v4"

# CONFIRMED 16 Aug 2026 from a live 401 response body: the key travels as a
# QUERY PARAMETER named 'apiKey', not as a header. Case-sensitive.
ODDSPAPI_AUTH_PARAM = "apiKey"

# Name of the environment variable holding the key. The key itself lives in
# .env and is never written here.
ODDSPAPI_KEY_ENV_VAR = "ODDSPAPI_API_KEY"

# Seconds between API calls. The API rate-limits at roughly 0.54s per
# endpoint and returns HTTP 429 with a retryMs value if you go faster.
# 1.5s gives headroom.
REQUEST_DELAY = 1.5

SPORT_ID_SOCCER = 10

# The /fixtures endpoint accepts sportId with from/to dates only if the range
# is under 10 days. A 21-day window is therefore fetched in three chunks.
FIXTURES_MAX_DATE_RANGE_DAYS = 9

# =============================================================
# MARKET AND OUTCOME IDS
# =============================================================
# CONFIRMED TWICE, independently:
#   - v1's config.py has used market "101" successfully for a month
#   - offline analysis 16 Aug 2026: 148 of 154 books carry market 101, and it
#     is the ONLY 3-outcome market betfair-ex carries. Its prices summed to an
#     implied probability of 1.002 - the signature of an exchange 1X2 book.
#
# NOTE: market "101" and outcome "101" are different things that happen to
# share a number. Separate named constants so they cannot be confused.

MARKET_ID_MATCH_ODDS = "101"   # the 1X2 / full-time result market

OUTCOME_HOME = "101"           # home win
OUTCOME_DRAW = "102"           # draw - never evaluated, see below
OUTCOME_AWAY = "103"           # away win

# Only the two team selections are evaluated. The draw can never trigger 2Up
# (no team to go two goals ahead), so backing and laying it is a guaranteed
# small loss with no upside.
TWO_UP_OUTCOMES = [OUTCOME_HOME, OUTCOME_AWAY]

# Outcome IDs follow the convention: base = home, +1 = draw, +2 = away.
# Confirmed by Betsson's bookmakerOutcomeId strings, which end -home, -draw
# and -away on outcomes 10761, 10762 and 10763 of market 10761.
OUTCOME_OFFSET_HOME = 0
OUTCOME_OFFSET_DRAW = 1
OUTCOME_OFFSET_AWAY = 2

# =============================================================
# BOOK REGISTRY
# =============================================================
# The heart of v2's multi-book support.
#
# 'promo_on_main_market' is the field that decides whether a signal from this
# book is real. bet365 pays out the STANDARD match-result bet early, so its
# market 101 price carries the promotion. For other books this is UNVERIFIED:
# if their early-payout offer lives in a separate market, their market 101
# price has no promotion attached, scenario 4 never fires, and every signal
# from them is a guaranteed small loss.
#
# Offline analysis 16 Aug 2026 found NO separate early-payout market anywhere
# in the OddsPapi feed. That means either the promotion applies to the main
# market (usable) or it is not in the feed at all (not usable). Resolving it
# requires reading each book's own promotional terms - it cannot be determined
# from the data.
#
# UNVERIFIED books are scanned and reported in clearly-marked columns. They
# are never mixed into the verified signal list.

PROMO_VERIFIED = "VERIFIED"
PROMO_UNVERIFIED = "UNVERIFIED"
PROMO_NONE = "NONE"

BOOK_REGISTRY = {
    "bet365": {
        "display_name": "bet365",
        "promo_on_main_market": PROMO_VERIFIED,
        "enabled_by_default": True,
        # Confirmed by the API's own error message, 15 Aug 2026.
        "max_tournaments_per_request": 5,
        "notes": "2Up pays out the standard match-result bet early.",
    },
    "paddypower": {
        "display_name": "Paddy Power",
        "promo_on_main_market": PROMO_UNVERIFIED,
        "enabled_by_default": False,
        # ASSUMED 5 (the general limit). Not yet proven for this book.
        "max_tournaments_per_request": 5,
        "notes": "Flutter platform. Early-payout terms not yet confirmed "
                 "against the standard market.",
    },
    "betuk": {
        "display_name": "BetUK",
        "promo_on_main_market": PROMO_UNVERIFIED,
        "enabled_by_default": False,
        "max_tournaments_per_request": 5,
        "notes": "Same odds as betmgm but UK-facing. The betmgm slug serves "
                 "sports.nj.betmgm.com (New Jersey) and is unusable from the "
                 "UK. Brand promotions may still differ from BetMGM UK's.",
    },
}

# The exchange, used only by the v1-style OddsPapi path. v2's primary lay
# source is the Betfair API directly - see the BETFAIR section below.
EXCHANGE_SLUG = "betfair-ex"
EXCHANGE_MAX_TOURNAMENTS_PER_REQUEST = 3

# Books scanned when no --books flag is given.
DEFAULT_BOOKS = [
    slug for slug, meta in BOOK_REGISTRY.items()
    if meta["enabled_by_default"]
]


def max_tournaments_for(slug):
    """
    Batch size for one bookmaker.

    The limit DIFFERS BY BOOKMAKER and exceeding it returns HTTP 400, which
    silently drops every league in that batch - so a wrong value here loses
    data without any visible error.
    """
    if slug == EXCHANGE_SLUG:
        return EXCHANGE_MAX_TOURNAMENTS_PER_REQUEST
    entry = BOOK_REGISTRY.get(slug)
    return entry["max_tournaments_per_request"] if entry else 5


# =============================================================
# LEAGUES
# =============================================================
# ONE ROW PER LEAGUE, holding both systems' IDs side by side.
#
# WHY A TABLE RATHER THAN TWO LISTS: OddsPapi and Betfair use entirely
# different IDs for the same competition. Two parallel lists would have to be
# kept in the same order by hand, and a single insertion in the wrong place
# would pair Premier League fixtures with La Liga markets. One row per league
# makes that impossible.
#
# Betfair IDs read from list_competitions on 16 Aug 2026. Re-verify each
# season - both systems' IDs can change.
#
# NAME TRAPS - never match a competition by name:
#   - Betfair 59 is German Bundesliga; 61 is Bundesliga 2.
#   - "Serie A" appears twice: Betfair 81 is Italian, 13 is Brazilian.
#   - The OddsPapi feed contains "Simulated Reality League" (32217, 32221,
#     32223) and "Virtual Football" (34616), which mimic real competitions
#     but are computer simulations.

LEAGUES = [
    {
        "oddspapi_id": 17,
        "betfair_id": "10932509",
        "name": "English Premier League",
        "note": "",
    },
    {
        "oddspapi_id": 18,
        "betfair_id": "7129730",
        "name": "English Championship",
        "note": "Betfair calls it 'English Sky Bet Championship'.",
    },
    {
        "oddspapi_id": 36,
        "betfair_id": "105",
        "name": "Scottish Premiership",
        "note": "EXPECTED TO MATCH NOTHING. Betfair lists 1 market in total "
                "for this competition, confirmed on their site as well. "
                "bet365 prices it; the exchange does not. Costs nothing to "
                "keep - it rides inside an existing bet365 batch.",
    },
    {
        "oddspapi_id": 8,
        "betfair_id": "117",
        "name": "Spanish La Liga",
        "note": "",
    },
    {
        "oddspapi_id": 35,
        "betfair_id": "59",
        "name": "German Bundesliga",
        "note": "Top flight only. NOT Betfair 61 / OddsPapi 44, which are "
                "Bundesliga 2.",
    },
    {
        "oddspapi_id": 23,
        "betfair_id": "81",
        "name": "Italian Serie A",
        "note": "Italy's. Brazil's Serie A is the row below.",
    },
    {
        "oddspapi_id": 34,
        "betfair_id": "55",
        "name": "French Ligue 1",
        "note": "",
    },
    {
        "oddspapi_id": 325,
        "betfair_id": "13",
        "name": "Brazilian Serie A",
        "note": "Mid-season during the European break.",
    },
]

# Candidate, not yet enabled: Brazilian Serie B, OddsPapi 390 / Betfair 321319.
# 2Up-eligible and the busiest league available. Add once v2 is stable.
#
# REMOVED FROM v1: English League One (OddsPapi 24) and League Two (25).
# Neither returns odds from any bookmaker via OddsPapi despite 540 future
# fixtures each. Betfair DOES carry them (competitions 35 and 37), which
# confirms the gap is OddsPapi's coverage, not a Betfair limitation.

TOURNAMENT_IDS = [league["oddspapi_id"] for league in LEAGUES]
BETFAIR_COMPETITION_IDS = [league["betfair_id"] for league in LEAGUES]

# Lookups in both directions, so neither side has to know the other's order.
BETFAIR_ID_BY_TOURNAMENT = {
    league["oddspapi_id"]: league["betfair_id"] for league in LEAGUES
}
TOURNAMENT_BY_BETFAIR_ID = {
    league["betfair_id"]: league["oddspapi_id"] for league in LEAGUES
}
LEAGUE_NAME_BY_TOURNAMENT = {
    league["oddspapi_id"]: league["name"] for league in LEAGUES
}


def betfair_id_for(tournament_id):
    """Betfair competition ID for an OddsPapi tournament ID, or None."""
    return BETFAIR_ID_BY_TOURNAMENT.get(tournament_id)


def tournament_id_for(betfair_id):
    """OddsPapi tournament ID for a Betfair competition ID, or None."""
    return TOURNAMENT_BY_BETFAIR_ID.get(str(betfair_id))


# =============================================================
# STAKING AND FILTER
# =============================================================

BACK_STAKE = 100.0    # $100 - makes every other column read as a percentage

# Worst-case result as a fraction of back stake, expressed as PROFIT AND LOSS:
# negative means a loss. A selection qualifies if its worst case is this good
# or better. Commission is deliberately excluded - rates vary by user and
# Smarkets charges none.
#
# WARNING - THIS SETTING IS THE STRATEGY, NOT A DISPLAY OPTION.
# Profit comes only when the team goes 2 goals clear then FAILS to win.
# Writing p for the chance of that, and B for the back odds:
#
#       EV = stake x (p x B  -  loss threshold)
#
# Estimated p x B sits around 0.038 across favourites and underdogs alike,
# so breakeven is a threshold of roughly 3.5% to 4%:
#
#       threshold 2%  ->  about +$1.80 per $100 staked
#       threshold 3%  ->  about +$0.80
#       threshold 4%  ->  about -$0.20
#       threshold 5%  ->  about -$1.20   <- current setting
#
# That p estimate is reasoned, not measured, so 5% is a DISCOVERY setting -
# good for seeing how the market is priced - rather than a licence to bet
# everything that qualifies. Tighten it before staking real money, or measure
# p from logged results first.
MAX_LOSS = -0.05

# How far ahead to scan, in days. A client-side filter, so widening costs
# nothing in requests.
FIXTURE_WINDOW_DAYS = 21

# =============================================================
# LADDER PRICING  (new in v2)
# =============================================================
# v1 assumed the best lay price held for the whole stake. It does not. If only
# 10 sits at the best price, the rest fills further down the ladder at worse
# prices, quietly pushing the real worst case past MAX_LOSS.
#
# v2 walks down the depth levels and computes the TRUE ACHIEVABLE price for
# filling the full required lay stake - a size-weighted average of the levels
# actually consumed. Some v1 signals will disappear as a result. That is the
# point of the exercise.

# If True, a selection is rejected when the visible ladder cannot fill the
# whole required lay stake. If False, it is reported with a shortfall warning.
REQUIRE_FULL_LADDER_FILL = True

# Fallback minimum size at the best lay price, used only when ladder pricing
# is unavailable. Mirrors BACK_STAKE because for any qualifying selection
# B/L is roughly 1, so the required lay stake lands near the back stake.
MIN_LAY_SIZE = 100.0

# Exchange sizes are reported in the Betfair ACCOUNT currency, which for a UK
# account is GBP - not dollars. v1's output labelled these "$", which was
# wrong. Stakes we choose ourselves are in dollars; sizes we read from the
# exchange are in pounds.
STAKE_CURRENCY_SYMBOL = "$"
EXCHANGE_CURRENCY_SYMBOL = "GBP"

# =============================================================
# BETFAIR EXCHANGE  (direct API - v2's lay source)
# =============================================================
# Auth and certificates are already solved by scripts/test_betfair.py.
# Environment variable names only - never the values.

BETFAIR_KEY_ENV_VAR = "BETFAIR_API_KEY"
BETFAIR_USERNAME_ENV_VAR = "BETFAIR_USERNAME"
BETFAIR_PASSWORD_ENV_VAR = "BETFAIR_PASSWORD"

# SENSITIVE - these files authenticate you to an account holding real money.
# They are gitignored and must stay that way. Never paste their contents
# anywhere, including into this chat.
BETFAIR_CERT_DIR = "certs"
BETFAIR_CERT_FILE = "client-2048.crt"
BETFAIR_KEY_FILE = "client-2048.key"

# Betfair meters per-request WEIGHT against a 200-point cap, not a monthly
# quota. Full-ladder data costs more weight per market than best-offers, so
# fewer markets fit in one call. The exact figures are to be measured on your
# own account rather than trusted from documentation - MARKETS_PER_BOOK_CALL
# is deliberately conservative until then.
BETFAIR_PRICE_PROJECTION = "EX_ALL_OFFERS"
BETFAIR_MARKETS_PER_BOOK_CALL = 10
BETFAIR_MARKET_TYPE = "MATCH_ODDS"

# Betfair's event type ID for football, confirmed by list_event_types.
BETFAIR_EVENT_TYPE_SOCCER = "1"

# =============================================================
# TEAM NAME CACHE AND MATCHING
# =============================================================
# Betfair uses its own event names and market IDs. OddsPapi's shared fixtureId
# does not exist on the Betfair side, so fixtures must be matched on team
# names across two sources with different conventions.
#
# A MISMATCH PAIRS ONE TEAM'S BACK PRICE WITH ANOTHER TEAM'S LAY PRICE AND
# PRODUCES A CONVINCING FAKE ARBITRAGE. Exact match or reject. Never guess.

TEAM_CACHE_PATH = "data/teams.json"
TEAM_CACHE_REFRESH_DAYS = 7
TEAM_ALIAS_PATH = "data/team_aliases.json"

# Kick-off times must agree within this many minutes for two fixtures to be
# considered the same match. A filter to narrow candidates only - NEVER
# sufficient on its own, because English football routinely has five or six
# matches kicking off at 15:00 on a Saturday.
KICKOFF_TOLERANCE_MINUTES = 30

# Both teams must match after normalisation. One-sided matches are rejected.
REQUIRE_BOTH_TEAMS_MATCH = True

# Every rejected pairing is written here so the alias table can be grown by
# hand. An unmatched fixture costs one missed signal; a mismatched one costs
# real money.
UNMATCHED_LOG_PATH = "logs/2upv2_unmatched.csv"

# =============================================================
# OUTPUT
# =============================================================

OUTPUT_DIR = "outputs"
RAW_DIR = "data/raw"
SIGNAL_LOG_PATH = "logs/2upv2_signals.csv"

# Only qualifying signals are logged, not every scan. Full-scan logging was
# rejected as excessive.
LOG_QUALIFYING_ONLY = True


# =============================================================
# SELF-CHECK
# =============================================================


def describe():
    """Print the active settings. Run this file directly to see them."""
    lines = []
    lines.append("=" * 70)
    lines.append("2upbotv2 CONFIGURATION")
    lines.append("=" * 70)
    lines.append(f"  Market:            {MARKET_ID_MATCH_ODDS} (full-time result)")
    lines.append(f"  Outcomes scanned:  {TWO_UP_OUTCOMES} (draw excluded)")
    lines.append(f"  Back stake:        {STAKE_CURRENCY_SYMBOL}{BACK_STAKE:.0f}")
    lines.append(f"  Max loss:          {MAX_LOSS:.1%}")
    lines.append(f"  Fixture window:    {FIXTURE_WINDOW_DAYS} days")
    lines.append(f"  Full ladder fill:  {REQUIRE_FULL_LADDER_FILL}")

    lines.append("")
    lines.append(f"  LEAGUES ({len(LEAGUES)}):")
    lines.append(f"    {'OddsPapi':<10}{'Betfair':<12}Name")
    for league in LEAGUES:
        lines.append(f"    {league['oddspapi_id']:<10}"
                     f"{league['betfair_id']:<12}{league['name']}")

    lines.append("")
    lines.append("  BOOKS:")
    for slug, meta in BOOK_REGISTRY.items():
        default = "ON " if meta["enabled_by_default"] else "off"
        lines.append(f"    {default} {slug:<12} "
                     f"promo={meta['promo_on_main_market']:<10} "
                     f"batch={meta['max_tournaments_per_request']}")

    lines.append("")
    lines.append(f"  Default books:     {DEFAULT_BOOKS}")

    # Request cost, so the budget consequence of enabling a book is visible.
    lines.append("")
    lines.append("  ODDSPAPI COST PER RUN (team names cached):")
    for count in range(1, len(BOOK_REGISTRY) + 1):
        slugs = list(BOOK_REGISTRY.keys())[:count]
        calls = 0
        for slug in slugs:
            batch = max_tournaments_for(slug)
            calls += -(-len(TOURNAMENT_IDS) // batch)  # ceiling division
        runs = 250 // calls if calls else 0
        lines.append(f"    {count} book(s) {str(slugs):<44} "
                     f"{calls} requests -> ~{runs} runs/month")

    return "\n".join(lines)


def validate():
    """
    Fail loudly on settings that would produce wrong results silently.

    Assertions are cheap insurance. A typo in an outcome ID would not crash
    anything - it would just quietly price the wrong selection.
    """
    assert OUTCOME_DRAW not in TWO_UP_OUTCOMES, \
        "The draw must never be evaluated - it cannot trigger 2Up."
    assert MAX_LOSS < 0, \
        "MAX_LOSS is a P&L figure; a positive value would demand a guaranteed profit."
    assert BACK_STAKE > 0, "BACK_STAKE must be positive."
    assert int(OUTCOME_HOME) + OUTCOME_OFFSET_DRAW == int(OUTCOME_DRAW), \
        "Outcome offsets disagree with the outcome IDs."
    assert int(OUTCOME_HOME) + OUTCOME_OFFSET_AWAY == int(OUTCOME_AWAY), \
        "Outcome offsets disagree with the outcome IDs."
    assert 24 not in TOURNAMENT_IDS and 25 not in TOURNAMENT_IDS, \
        "Leagues 24 and 25 were removed - no odds coverage."
    assert BOOK_REGISTRY["bet365"]["promo_on_main_market"] == PROMO_VERIFIED, \
        "bet365 is the only book with a confirmed main-market promotion."

    # League table integrity - a duplicate or a missing ID would pair one
    # competition's fixtures with another's markets.
    assert len(TOURNAMENT_IDS) == len(set(TOURNAMENT_IDS)), \
        "Duplicate OddsPapi tournament ID in LEAGUES."
    assert len(BETFAIR_COMPETITION_IDS) == len(set(BETFAIR_COMPETITION_IDS)), \
        "Duplicate Betfair competition ID in LEAGUES."
    for league in LEAGUES:
        assert league["oddspapi_id"], f"Missing OddsPapi ID: {league['name']}"
        assert league["betfair_id"], f"Missing Betfair ID: {league['name']}"
        assert isinstance(league["betfair_id"], str), \
            f"Betfair IDs must be strings: {league['name']}"

    return True


if __name__ == "__main__":
    validate()
    print(describe())
    print("")
    print("=" * 70)
    print("CONFIG OK")
    print("=" * 70)