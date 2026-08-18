# config_freeze.py
"""
Configuration for the Sky Bet Acca Freeze screener.

Standalone, following the config_v2.py precedent — editing this cannot
disturb 2up_bot or 2upbotv2.

WHAT THIS BOT DOES
  Finds teams priced 7.00 (6/1) or longer to win a match in an
  Acca-Freeze-eligible competition, then compares that price against the
  same team's First Team To Score price. A big gap means the freeze
  converts a long-odds "win" bet into a much likelier "take the lead" bet
  while still paying the win price.

Secrets live in .env and are read by the runner, never here.
"""

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

ODDSPAPI_BASE_URL = "https://api.oddspapi.io/v4"
SPORT_ID_SOCCER = 10

# Sky Bet is NOT in the OddsPapi feed — confirmed against all 154 bookmakers
# on 18 Aug 2026. Paddy Power is the proxy: same Flutter group, soft UK book.
# Every output column sourced from it is labelled a PROXY, never a Sky price.
MATCH_ODDS_BOOKMAKER = "paddypower"

# Tournament IDs per /odds-by-tournaments call.
TOURNAMENTS_PER_REQUEST = 5

# Seconds between requests. Matches config.py.
REQUEST_DELAY = 1.5

# ---------------------------------------------------------------------------
# Markets
#
# Outcome IDs run consecutively from the market ID. CRITICAL: the two
# markets do NOT share an outcome order.
#
#   101 (match odds):  HOME / DRAW / AWAY
#   10216 (FTTS):      HOME / NO GOAL / AWAY   <-- no-goal in the MIDDLE
#
# Reading FTTS positionally as if it were 1X2 pairs the away team with the
# no-goal price. Identified 18 Aug 2026 from sbobet's HF/NG/AF coding;
# market 10219 is the LAST-team-to-score market and must never be used.
# ---------------------------------------------------------------------------

MARKET_MATCH_ODDS = "101"
OUTCOME_MATCH_HOME = "101"
OUTCOME_MATCH_DRAW = "102"
OUTCOME_MATCH_AWAY = "103"

MARKET_FTTS = "10216"
OUTCOME_FTTS_HOME = "10216"
OUTCOME_FTTS_NO_GOAL = "10217"
OUTCOME_FTTS_AWAY = "10218"

# ---------------------------------------------------------------------------
# Screening thresholds
# ---------------------------------------------------------------------------

# Minimum match-odds price to qualify. 7.00 decimal = 6/1 fractional.
# Raised from 6.00 on 18 Aug 2026 to cut request cost.
# Draws are never evaluated — you cannot freeze a draw.
MIN_MATCH_ODDS = 7.00

# The headline gate: (match_odds - ftts_odds) / ftts_odds >= 0.80
# expressed as a ratio, match_odds / ftts_odds >= 1.80.
# A 7.00 shot needs FTTS at 3.89 or shorter to pass.
MIN_RATIO = 1.80

# Floor on the implied probability of the team scoring first.
# Stops very long shots with enormous ratios but almost no chance of ever
# triggering the freeze. 0.20 implies FTTS odds of 5.00 or shorter.
# STARTING DEFAULT — tune this after a few weeks of real candidates.
P_FTTS_FLOOR = 0.20

# ---------------------------------------------------------------------------
# Eligible competitions — 36 of the 39 on Sky Bet's list.
#
# Excluded by decision on 18 Aug 2026: World Cup 2026, UEFA Women's EURO
# 2025, Nations League (representative-team tournaments).
#
# NOT eligible despite being in 2up_bot's config: Brasileiro Serie B (390).
# Do not copy tournament IDs between bots.
# ---------------------------------------------------------------------------

FREEZE_TOURNAMENTS = {
    # England
    17: "Premier League",
    18: "Championship",
    24: "League One",
    25: "League Two",
    173: "National League",
    19: "FA Cup",
    21: "EFL Cup (Carabao)",
    346: "Community Shield",

    # Scotland
    36: "Scottish Premiership",
    206: "Scottish Championship",

    # Spain
    8: "LaLiga",
    54: "LaLiga 2 (Segunda)",          # Spain — not to be confused with 53
    213: "Supercopa (Spanish Super Cup)",

    # Italy
    23: "Serie A",
    53: "Serie B",                     # Italy — not to be confused with 54
    341: "Supercoppa (Italian Super Cup)",

    # Germany
    35: "Bundesliga",
    44: "2. Bundesliga",
    799: "German Super Cup",

    # France
    34: "Ligue 1",
    182: "Ligue 2",
    339: "Trophee des Champions (French Super Cup)",

    # Netherlands
    37: "Eredivisie",
    131: "Eerste Divisie",

    # Portugal
    238: "Liga Portugal (Primeira Liga)",

    # Belgium
    38: "Pro League (Jupiler)",

    # Turkiye
    52: "Super Lig",

    # Brazil
    325: "Brasileiro Serie A",

    # Argentina
    155: "Liga Profesional",

    # USA
    242: "MLS",

    # Australia
    136: "A-League",

    # International Clubs
    7: "UEFA Champions League",
    679: "UEFA Europa League",
    34480: "UEFA Conference League",
    465: "UEFA Super Cup",
    357: "FIFA Club World Cup",
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

# Own subfolder, so freeze runs don't mix with 2up_bot's output.
OUTPUT_DIR = "output/freeze"

# Fixed-name copy of the newest workbook, overwritten every run. The
# timestamped archive still builds up alongside it — this is just the one
# you open without hunting.
LATEST_WORKBOOK = "latest.xlsx"

LOG_DIR = "logs"
SIGNAL_LOG = "logs/freeze_signals.csv"
RAW_DIR = "data/raw"

# Keep every scanned selection, not just passing ones, so the log can show
# what the thresholds rejected when you review it in three months.
LOG_ALL_CANDIDATES = True