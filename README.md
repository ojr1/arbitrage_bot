# 1_my_betting_bot

A systematic EV signal engine built in Python, executed on command. The bot queries a hybrid
basket of global exchanges, prediction markets and sportsbooks to construct a consensus implied
probability, then evaluates each target outcome against a four-tier model funnel to identify
value betting opportunities. Capital allocation is governed by a Dynamic Fractional Kelly
framework that scales stake size to signal quality. Results are written to a timestamped
Excel file in `outputs/`.

Full model specification: see `whitepaper.md`.
Full task tracking: see `plan.md`.

---

## Architecture

```
LAYER 1 — Core Data Infrastructure (core.py)
    └── fetch_oddspapi()    → all basket seat prices in one call
    └── fetch_smarkets()    → back and lay prices (pending approval)
    └── compute_s_idx()     → mean IP across 17 UK soft books
    └── build_basket()      → IP_bar per outcome per fixture

LAYER 2 — Analytics (each bot calls core.py)
    └── match_odds_bot      → EV signal engine, signal tiers, Kelly staking
    └── 2up_bot             → back vs lay arb detection (pending Smarkets)
    └── player_props_bot    → single outcome signal engine
```

---

## Data Sources

| Source     | Type              | Role in Production                          |
| :--------- | :---------------- | :------------------------------------------ |
| OddsPapi   | Aggregator        | Primary source — all basket seats in one call |
| Smarkets   | Exchange          | Back and lay prices; direct API (pending)   |
| Betfair    | Exchange          | Reference and testing only                  |
| Polymarket | Prediction Market | Reference and testing only                  |
| Kalshi     | Prediction Market | Reference and testing only                  |

OddsPapi provides Bet365, Pinnacle, Betfair Exchange (back + lay), Kalshi, Polymarket
and ~17 UK soft books for `S_idx` in a single API call.

---

## Market Modules

| Module              | Market Type             | M4 Eligible | Status        |
| :------------------ | :---------------------- | :---------- | :------------ |
| `match_odds_bot`    | Match result odds       | Yes         | In progress   |
| `2up_bot`           | 2-Up promotion markets  | Yes         | Pending Smarkets |
| `player_props_bot`  | Player proposition bets | No          | Pending PL season (Aug 2026) |

---

## Signal Tiers

| Tier      | Models Required | Description                           |
| :-------- | :-------------- | :------------------------------------ |
| Standard  | M1              | Value against raw consensus           |
| Buffered  | M1, M2          | Survives 7.5% margin buffer           |
| Confirmed | M1, M2, M3      | Survives 10% margin buffer            |
| Elite     | M1, M2, M3, M4  | Survives full overround normalisation |

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/1_my_betting_bot.git
cd 1_my_betting_bot
```

### 2. Create and activate a virtual environment

```bash
python -m venv venv
venv\Scripts\activate     # Windows
source venv/bin/activate  # Mac / Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` and fill in your API keys and credentials:

```bash
cp .env.example .env      # Mac / Linux
copy .env.example .env    # Windows
```

---

## Project Structure

```
1_my_betting_bot/
├── core.py                   ← Shared data infrastructure (Layer 1)
├── scripts/
│   ├── match_odds_bot/
│   │   └── run.py            ← Signal engine analytics (Layer 2)
│   ├── 2up_bot/
│   │   └── run.py            ← Arb detection analytics (Layer 2)
│   └── player_props_bot/
│       └── run.py            ← Props signal analytics (Layer 2)
├── data/
│   ├── raw/                  ← Raw API responses; never modified after ingestion
│   └── processed/            ← Cleaned data ready for signal engine
├── logs/                     ← Execution logs
├── tests/                    ← Unit tests for each module
├── outputs/                  ← Timestamped Excel signal output per run
├── certs/                    ← Betfair SSL certificates (not committed)
├── config.py                 ← Project-wide constants and S_idx list
├── .env                      ← API keys and credentials (not committed)
├── .env.example              ← Safe placeholder template
└── requirements.txt          ← Python dependencies
```

---

## Status

See `plan.md` for the full phase breakdown and task tracking.