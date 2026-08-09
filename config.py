# config.py
# Project-wide constants for 1_my_betting_bot
# All hardcoded values live here; do not define them inside individual scripts

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

# --- SEATS RETURNING IMPLIED PROBABILITY DIRECTLY ---
# OddsPapi normalises all sources to decimal odds — leave empty
IP_FORMAT_SEATS = []

# --- S_IDX CONFIGURATION (4 core UK soft books) ---
S_IDX_BOOKS = [
    "williamhill",
    "ladbrokes",
    "paddypower",
    "betway",
]