# config.py
# Project-wide constants for arbitrage_bot
# All hardcoded values live here; do not define them inside individual scripts

# =============================================================
# SHARED - used by more than one bot
# =============================================================

# --- ODDSPAPI ---
ODDSPAPI_BASE_URL = "https://api.oddspapi.io/v4"

# Seconds to pause between API calls. The API rate-limits at roughly 0.54s
# per endpoint and returns HTTP 429 if you go faster. 1.5s gives headroom.
REQUEST_DELAY = 1.5

# OddsPapi sport IDs
SPORT_ID_SOCCER = 10

# The /odds-by-tournaments endpoint limits how many tournament IDs you may
# request at once - and the limit DIFFERS BY BOOKMAKER. Both confirmed by the
# API's own error messages, 15 Aug 2026:
#   "Please provide a maximum of 5 tournament IDs"
#   "Please provide a maximum of 3 tournament IDs ... for 'betfair-ex'"
# Exceeding it returns HTTP 400 for that batch, which silently loses every
# league in it - so these must be right.
MAX_TOURNAMENTS_PER_REQUEST = 5

MAX_TOURNAMENTS_BY_BOOKMAKER = {
    "betfair-ex": 3,
}


def max_tournaments_for(bookmaker):
    """Batch size for one bookmaker, falling back to the general limit."""
    return MAX_TOURNAMENTS_BY_BOOKMAKER.get(bookmaker, MAX_TOURNAMENTS_PER_REQUEST)


# The /fixtures endpoint is different again - it takes ONE tournamentId only,
# and rejects the plural 'tournamentIds' name entirely. It does accept sportId
# with from/to dates, but only if those dates are UNDER 10 days apart:
#   "'to' and 'from' must be under 10 days apart when only 'sportId' is provided."
# So a 21-day window is fetched as three chunks of 9 days.
FIXTURES_MAX_DATE_RANGE_DAYS = 9

# --- MARKET AND OUTCOME IDS ---
# NOTE: market "101" and outcome "101" are different things that happen to
# share a number. Kept as separate named constants so they cannot be confused.
MARKET_ID_MATCH_ODDS = "101"   # the 1X2 / full-time result market

OUTCOME_HOME = "101"           # home win
OUTCOME_DRAW = "102"           # draw - NOT used by 2up_bot (see below)
OUTCOME_AWAY = "103"           # away win

# --- BETFAIR EXCHANGE FIELD NAMES ---
# Confirmed from live API response 15 Aug 2026. The exchangeMeta block uses
# "availableToBack" / "availableToLay" - NOT "back" / "lay".
# Each is a list of up to 3 price levels, each a dict of {price, size}.
EXCHANGE_BACK_KEY = "availableToBack"
EXCHANGE_LAY_KEY  = "availableToLay"


# =============================================================
# 2UP_BOT
# =============================================================

# --- LEAGUES TO SCAN ---
# Tournament IDs verified against the live feed 15 Aug 2026, and cross-checked
# against bet365's published 2Up-eligible competition list.
# Leagues only in v1 - cup competitions excluded for now.
TWO_UP_TOURNAMENT_IDS = [
    17,   # Premier League      England
    18,   # Championship        England
    24,   # League One          England
    25,   # League Two          England
    36,   # Premiership         Scotland
    8,    # LaLiga              Spain
    35,   # Bundesliga          Germany   (top flight only - NOT 2. Bundesliga, id 44)
    23,   # Serie A             Italy     (Italy's - Brazil's Serie A is 325, below)
    34,   # Ligue 1             France
    325,  # Brasileiro Serie A  Brazil    (mid-season now, unlike the European leagues)
]

# WARNING - do not add these by name-matching. The feed contains
# "Simulated Reality League" (ids 32217, 32221, 32223) and "Virtual Football"
# (id 34616) entries whose names look like real leagues but are computer
# simulations. Always verify a new ID against the country column first.

# --- BOOKMAKER SLUGS ---
TWO_UP_SOFT_BOOK = "bet365"      # the book offering the 2Up promotion
TWO_UP_EXCHANGE  = "betfair-ex"  # where we lay the same selection

# --- STAKING AND FILTER ---
BACK_STAKE = 100.0    # $100 - makes every other column read as a percentage

# Worst-case result as a fraction of back stake, expressed as PROFIT AND LOSS:
# negative means a loss. A selection qualifies if its worst case is this good
# or better. -0.05 = "lose no more than 5% of stake". Commission is deliberately
# excluded - rates vary by user and Smarkets charges none.
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
# That p estimate is reasoned, not measured, so treat 5% as a DISCOVERY
# setting - good for seeing how the market is priced - rather than as a
# licence to bet everything that qualifies. Tighten it before staking real
# money, or measure p from logged results first.
MAX_LOSS = -0.05

# How far ahead to scan, in days.
FIXTURE_WINDOW_DAYS = 21

# Minimum money that must be available at the best lay price for a selection
# to be reported. Set to 0 to disable this filter.
# Read from exchangeMeta.availableToLay[0].size.
#
# WHY THIS SHOULD TRACK BACK_STAKE:
# The lay stake is (B x S) / L. For any selection that qualifies, B and L are
# within about 5% of each other, so B/L is roughly 1 and the lay stake always
# lands close to the back stake itself. Needing 100 available for a 100 back
# stake is therefore the right test, not an arbitrary round number.
#
# Without this filter the reported price is OPTIMISTIC: if only 10 sits at the
# best lay price, the rest of your stake fills at worse prices further down the
# ladder, quietly pushing the real worst case past MAX_LOSS.
#
# NOTE: this size is in your Betfair account currency (GBP for a UK account),
# even though the output labels read as $.
MIN_LAY_SIZE = 100.0

# Only the two team selections are evaluated. The draw can never trigger the
# 2Up promotion (no team to go two goals ahead), so backing and laying the draw
# is a guaranteed small loss with no upside.
TWO_UP_OUTCOMES = [OUTCOME_HOME, OUTCOME_AWAY]


# =============================================================
# MATCH_ODDS_BOT  (deferred - consensus basket work)
# =============================================================
# Left untouched. These belong to the parked quad-tier consensus engine.

# --- SIGNAL ENGINE ---
EV_THRESHOLD   = 0.10
VARIANCE_LIMIT = 0.10

# --- KELLY STAKING ---
AGGRESSION_M   = 1.0

# --- NAMED BASKET SEATS (OddsPapi slugs) ---
SEAT_BET365     = "bet365"
SEAT_PINNACLE   = "pinnacle"
SEAT_BETFAIR    = "betfair-ex"
SEAT_KALSHI     = "kalshi"
SEAT_POLYMARKET = "polymarket"

# --    - SEATS RETURNING IMPLIED PROBABILITY DIRECTLY ---
# OddsPapi normalises all sources to decimal odds - leave empty
IP_FORMAT_SEATS = []

# --- S_IDX CONFIGURATION ---
# UNRESOLVED CONFLICT: this list holds 4 books, but whitepaper.md section 2.2
# and plan.md both specify 17. Left as-is because match_odds_bot is deferred.
# Must be settled before the consensus engine is built.
S_IDX_BOOKS = [
    "williamhill",
    "ladbrokes",
    "paddypower",
    "betway",
]