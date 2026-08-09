# Plan: 1_my_betting_bot

## Overview

Signal engine operating across a hybrid basket of global exchanges, prediction markets and
sportsbooks; applying fixed-margin barriers and optional full overround normalisation to
identify model-validated EV opportunities.
Built in Python and executed on command, with automated API and data ingestion pipelines
constructing the consensus basket at the point of execution. Integrated Dynamic Fractional
Kelly framework scales capital allocation to signal quality, explicitly rewarding
high-probability value for systematic, risk-adjusted execution.

---

## Architecture

```
LAYER 1 — Core Data Infrastructure (core.py)
    └── fetch_oddspapi()    → all prices for all fixtures in one call
    └── fetch_smarkets()    → back and lay prices (once approved)
    └── compute_s_idx()     → mean IP across 17 UK soft books
    └── build_basket()      → IP_bar per outcome per fixture

LAYER 2 — Analytics (per bot, each calls core.py)
    └── match_odds_bot      → consensus signal engine, EV tiers, Kelly
    └── 2up_bot             → back vs lay arb detection (pending Smarkets)
    └── player_props_bot    → single outcome signal engine
```

---

## Status

| Phase | Description                          | Status      |
|-------|--------------------------------------|-------------|
| 1     | Setup & Environment                  | Complete    |
| 2     | API Research & Connectivity          | In Progress |
| 3     | Core Data Infrastructure             | Not Started |
| 4     | Analytics Layer                      | Not Started |
| 5     | Kelly Staking Module                 | Not Started |
| 6     | Excel Output                         | Not Started |
| 7     | Documentation & Review               | Not Started |

Status options: Complete | In Progress | Blocked | Not Started

---

## To-Do

### Phase 1 — Setup & Environment
- [x] Create folder structure per spec below
- [x] Create `.env` file for API keys and add to `.gitignore`
- [x] Create `.env.example` with placeholder keys
- [x] Create `.gitignore`
- [x] Create `requirements.txt`
- [x] Create `whitepaper.md` and `plan.md` in project root
- [x] Set up virtual environment (`venv`)
- [x] Install dependencies
- [x] Create `config.py` with project constants
- [ ] Initialise Git repo and push to GitHub

### Phase 2 — API Research & Connectivity

#### OddsPapi (Primary Aggregator — Production Source)
- [x] Research OddsPapi as primary aggregator
- [x] Sign up for free API key at oddspapi.io
- [x] Confirm Pinnacle, Bet365, Betfair Exchange, Kalshi, Polymarket all in feed
- [x] Confirmed Betfair Exchange returns back AND lay prices via exchangeMeta field
- [x] Confirmed Kalshi and Polymarket return implied probability format directly
- [x] Test connection and validate sample odds response
- [x] Retrieve match odds for all World Cup fixtures
- [x] Queried full bookmaker list for S_idx construction
- [x] Defined S_idx list — 17 UK soft books — documented in config.py
- [ ] Confirm player props market coverage — to be tested when PL season starts (Aug 2026)

#### Smarkets (Direct API — Production Source)
- [x] Email sent to api@smarkets.com requesting read-only access
- [x] Confirmed read-only data access use case (no automated trading)
- [ ] Awaiting API approval
- [ ] Review API documentation once approved
- [ ] Test connection and validate back and lay price response
- [ ] Map response fields to basket seat format

#### Betfair Exchange (Reference Only — Accessed via OddsPapi in Production)
- [x] Direct API tested and validated using betfairlightweight
- [x] Confirmed back prices retrievable via direct API
- [x] Confirmed back and lay prices available via OddsPapi feed
- [x] Decision: use OddsPapi for production; direct connection kept for reference

#### Polymarket (Reference Only — Accessed via OddsPapi in Production)
- [x] Gamma API tested and validated — no auth required
- [x] Confirmed role: tournament-level probability signals only
- [x] Decision: use OddsPapi for production; direct connection kept for reference

#### Kalshi (Reference Only — Accessed via OddsPapi in Production)
- [x] Public REST API tested and validated — no auth required
- [x] Series ticker for World Cup: KXWCGAME
- [x] Confirmed prices in implied probability format (0-1 scale)
- [x] Decision: use OddsPapi for production; direct connection kept for reference

#### Pinnacle
- [x] No public API since July 2025 — accessed exclusively via OddsPapi

#### Cross-Source Validation
- [x] All sources confirmed accessible via OddsPapi in a single call
- [x] S_idx bookmaker list defined — 17 UK soft books in config.py
- [ ] Run cross-validation script; confirm all basket seats return data for same fixture
- [ ] Document any market coverage gaps

### Phase 3 — Core Data Infrastructure

All shared functions live in `core.py` in the project root. Each bot calls these functions
rather than implementing its own data layer.

- [ ] Build `fetch_oddspapi()` — pull all fixture prices from OddsPapi in one call
- [ ] Build `fetch_smarkets()` — pull back and lay prices per fixture (pending approval)
- [ ] Build `compute_s_idx()` — mean IP across active S_idx soft books per fixture
- [ ] Build `build_basket()` — compute IP_bar per outcome per fixture across all seats
- [ ] Build `compute_basket_variance()` — coefficient of variation across active seats
- [ ] Handle IP conversion for decimal odds seats (Bet365, Pinnacle, Betfair, S_idx)
- [ ] Handle direct IP format for Kalshi and Polymarket (no conversion needed)
- [ ] Save raw OddsPapi response to data/raw/ after each run
- [ ] Validate basket output; confirm IP_bar values are sensible for known fixtures

### Phase 4 — Analytics Layer

Each bot has a single `run.py` file that calls `core.py` and applies its own analysis logic.

#### match_odds_bot
- [ ] Build `compute_ip()` — convert decimal odds to implied probability
- [ ] Build `compute_ip_bar()` — mean IP across active seats
- [ ] Build `compute_overround()` — sum of IP_bar across all outcomes (M4 only)
- [ ] Build `compute_pm1()` — raw consensus
- [ ] Build `compute_pm2()` — 7.5% fixed barrier
- [ ] Build `compute_pm3()` — 10% fixed barrier
- [ ] Build `compute_pm4()` — overround normalisation (build last; optional)
- [ ] Build `compute_ev()` — EV = (P_model x D_offered) - 1 for all models
- [ ] Build `assign_signal_tier()` — sequential EV > 10% check across M1 to M4
- [ ] Write edge case handlers; single active seat, missing prices
- [ ] Unit test each function independently before integration

#### 2up_bot (blocked — pending Smarkets approval)
- [ ] Build arb detection logic; compare Bet365 back vs Betfair lay and Smarkets lay
- [ ] Flag fixtures where back odds >= lay odds
- [ ] Output arb opportunities with both lay options shown

#### player_props_bot
- [ ] Scope player props markets once PL season starts (Aug 2026)
- [ ] Build single-outcome signal engine calling core.py

### Phase 5 — Kelly Staking Module
- [ ] Build `compute_kelly()` — baseline f* using P_adj (default P_M2)
- [ ] Build `compute_dynamic_multiplier()` — L = M x P_adj
- [ ] Build `compute_final_stake()` — f_final = f* x (M x P_adj)
- [ ] Build `compute_stake_amount()` — f_final x liquid bankroll
- [ ] Build bankroll input handler; manual refresh every 24 hours
- [ ] Test staking output against Example Table in whitepaper Section 7.3

### Phase 6 — Excel Output
- [ ] Build output emitter; write all signal fields to Excel using openpyxl
- [ ] Format Excel output; column headers, number formatting, conditional formatting for tiers
- [ ] Flag high-variance basket signals for manual review
- [ ] Save timestamped file to outputs/ on each run
- [ ] Validate output against whitepaper Step 8 field list

### Phase 7 — Documentation & Review
- [ ] Update `README.md` with project summary and usage instructions
- [ ] Add inline comments to all scripts
- [ ] Final end-to-end test across all phases
- [ ] Sign off and mark MVP Complete

---

## Tech Stack

| Tool               | Purpose                                                        |
|--------------------|----------------------------------------------------------------|
| Python             | Data ingestion, signal engine, staking logic                   |
| openpyxl           | Excel output (.xlsx)                                           |
| betfairlightweight | Betfair direct API client (reference/testing only)             |
| VS Code            | Development environment                                        |
| GitHub             | Version control                                                |
| OddsPapi           | Primary production source; all basket seats in one call        |
| Smarkets API       | Back and lay prices; direct API (approval pending)             |

---

## Technical Research

API documentation:
- OddsPapi: https://oddspapi.io/en/docs
- Betfair: https://developer.betfair.com (reference only)
- Smarkets: https://docs.smarkets.com (access pending)
- Polymarket: https://docs.polymarket.com (reference only)
- Kalshi: https://docs.kalshi.com/welcome (reference only)

Key findings:
- Pinnacle: no public API since July 2025 — accessed via OddsPapi
- Kalshi: UK account creation blocked but read-only API publicly accessible
- Polymarket: Gamma API fully public, no auth required
- Kalshi World Cup series ticker: KXWCGAME
- Kalshi and Polymarket prices in implied probability format (no conversion needed)
- OddsPapi free tier: 250 requests/month; one call returns all 350+ bookmakers
- OddsPapi returns Betfair Exchange back AND lay prices via exchangeMeta field
- Betfair Delayed App Key: free, 1-3 minute delay — kept for reference/testing only
- PostgreSQL and DBeaver shelved — output to Excel via openpyxl instead
- All basket seats except Smarkets accessed via OddsPapi in production

S_idx bookmaker list (17 UK soft books — defined in config.py):
888sport, betmgm.co.uk, betway, bwin, casumo, coral, grosvenor, ladbrokes,
leovegas, lottoland, netbet, paddypower, pokerstars.uk, sportingbet,
unibet, virginbet, williamhill

---

## File Structure

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
│   │   └── .gitkeep
│   └── processed/            ← Cleaned data ready for signal engine
│       └── .gitkeep
├── logs/                     ← Execution logs
│   └── .gitkeep
├── tests/                    ← Unit tests for each module
│   └── .gitkeep
├── outputs/                  ← Timestamped Excel signal output per run
│   └── .gitkeep
├── certs/                    ← Betfair SSL certificates (not committed)
├── .env                      ← API keys and credentials (not committed)
├── .env.example              ← Safe placeholder template
├── .gitignore
├── config.py                 ← Project-wide constants and S_idx list
├── requirements.txt
├── README.md
├── plan.md
└── whitepaper.md
```