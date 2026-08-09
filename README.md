# arbitrage_bot

A systematic expected-value signal engine for sports betting markets, built in Python.

The bot queries a hybrid basket of exchanges, prediction markets and sportsbooks to build a
consensus view of true probability, then flags outcomes priced meaningfully above that
consensus. Stake sizing is governed by a Dynamic Fractional Kelly framework that scales
allocation to signal quality. Results are written to a timestamped Excel file in `outputs/`.

The underlying idea: individual bookmakers misprice markets, but the aggregate of sharp
sources (exchanges and prediction markets, where participants are financially exposed to
being wrong) is a far better probability estimate than any single book. Where a book's
price implies a probability materially below that consensus, there is positive expected
value in taking it.

**Full mathematical specification:** [whitepaper.md](whitepaper.md)
**Development roadmap and task tracking:** [plan.md](plan.md)

---

## Architecture

Two layers. Layer 1 handles all external data and produces a single normalised view of the
market; Layer 2 contains the analytics, with each module consuming Layer 1 rather than
querying APIs directly.

```
LAYER 1 -- Core Data Infrastructure (core.py)
    |-- fetch_oddspapi()    -> all basket seat prices in one call
    |-- fetch_smarkets()    -> back and lay prices (pending approval)
    |-- compute_s_idx()     -> mean implied probability across ~17 UK soft books
    |-- build_basket()      -> IP_bar (consensus probability) per outcome per fixture

LAYER 2 -- Analytics (each module calls core.py)
    |-- match_odds_bot      -> EV signal engine, signal tiers, Kelly staking
    |-- 2up_bot             -> back vs lay arbitrage detection (pending Smarkets)
    |-- player_props_bot    -> single-outcome signal engine
```

---

## Data Sources

| Source     | Type              | Role in Production                             |
| :--------- | :---------------- | :--------------------------------------------- |
| OddsPapi   | Aggregator        | Primary source -- all basket seats in one call |
| Smarkets   | Exchange          | Back and lay prices; direct API (pending)      |
| Betfair    | Exchange          | Reference and testing only                     |
| Polymarket | Prediction Market | Reference and testing only                     |
| Kalshi     | Prediction Market | Reference and testing only                     |

OddsPapi supplies Bet365, Pinnacle, Betfair Exchange (back and lay), Kalshi, Polymarket and
approximately 17 UK soft books for the `S_idx` calculation in a single API call. Direct
integrations with Betfair, Kalshi and Polymarket exist for cross-validation of aggregator
pricing.

---

## Market Modules

| Module              | Market Type             | M4 Eligible | Status                                    |
| :------------------ | :---------------------- | :---------- | :---------------------------------------- |
| `match_odds_bot`    | Match result odds       | Yes         | In progress                               |
| `2up_bot`           | 2-Up promotion markets  | Yes         | Blocked -- awaiting Smarkets API approval |
| `player_props_bot`  | Player proposition bets | No          | Planned -- 2026/27 PL season              |

---

## Signal Tiers

Each candidate signal is tested against a cumulative model funnel. Higher tiers survive
progressively more conservative assumptions about bookmaker margin, so tier is a proxy for
confidence rather than for edge size.

| Tier      | Models Required | Description                           |
| :-------- | :-------------- | :------------------------------------ |
| Standard  | M1              | Value against raw consensus           |
| Buffered  | M1, M2          | Survives 7.5% margin buffer           |
| Confirmed | M1, M2, M3      | Survives 10% margin buffer            |
| Elite     | M1, M2, M3, M4  | Survives full overround normalisation |

See [whitepaper.md](whitepaper.md) for the derivation of each model.

---

## Tech Stack

- **Python** -- core application
- **requests** -- REST API integration across five data providers
- **openpyxl** -- timestamped Excel output
- **python-dotenv** -- environment-based credential management
- **cryptography** -- self-signed certificate generation for Betfair's non-interactive login

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/ojr1/arbitrage_bot.git
cd arbitrage_bot
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

Copy `.env.example` to `.env` and populate it with your own API credentials:

```bash
copy .env.example .env    # Windows
cp .env.example .env      # Mac / Linux
```

No credentials are committed to this repository. All secrets are read from the environment
at runtime; `.env` and `certs/` are excluded via `.gitignore`.

### 5. Generate Betfair certificates (optional)

Only required if using the direct Betfair integration. Betfair's non-interactive login
endpoint requires a self-signed certificate pair, which must be uploaded to your Betfair
account before use.

```bash
python generate_certs.py
```

---

## Repository Structure

```
arbitrage_bot/
|-- core.py                 <- Shared data infrastructure (Layer 1)
|-- config.py               <- Project-wide constants and S_idx bookmaker list
|-- generate_certs.py       <- Betfair SSL certificate generation
|-- scripts/                <- API integration and connectivity tests
|-- tests/                  <- Unit tests
|-- whitepaper.md           <- Mathematical specification
|-- plan.md                 <- Development roadmap
|-- requirements.txt        <- Python dependencies
|-- .env.example            <- Credential template (no real values)
`-- .gitignore
```

Directories created at runtime and excluded from version control:

```
data/raw/          <- Raw API responses; never modified after ingestion
data/processed/    <- Cleaned data ready for the signal engine
outputs/           <- Timestamped Excel signal output per run
logs/              <- Execution logs
certs/             <- Betfair SSL certificates
```

---

## Status

Active development. Layer 1 core infrastructure and the consensus basket construction are
built; API connectivity is verified against all five data sources. The `match_odds_bot`
analytics module is in progress.

See [plan.md](plan.md) for the full phase breakdown.

---

## Disclaimer

This project is a personal research exercise in quantitative modelling and API integration.
It is not financial advice and carries no guarantee of profitability.