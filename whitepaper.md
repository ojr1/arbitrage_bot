# Quad-Tier Signal Confluence Framework

**Project:** `arbitrage_bot`
**Focus:** Global Consensus Modelling & Value Detection
**Status:** Active Development

---

## Overview

Signal engine operating across a hybrid basket of global exchanges, prediction markets and
sportsbooks; applying fixed-margin barriers and optional full overround normalisation to
identify model-validated EV opportunities.
Built in Python and executed on command, with automated API and data ingestion pipelines
constructing the consensus basket at the point of execution. Integrated Dynamic Fractional
Kelly framework scales capital allocation to signal quality, explicitly rewarding
high-probability value for systematic, risk-adjusted execution.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [The Hybrid Consensus Basket](#2-the-hybrid-consensus-basket)
3. [Mathematical Glossary & Definitions](#3-mathematical-glossary--definitions)
4. [The Quad-Tier Model Logic](#4-the-quad-tier-model-logic)
5. [Expected Value & Signal Tiers](#5-expected-value--signal-tiers)
6. [Data Convergence & Signal Confidence](#6-data-convergence--signal-confidence)
7. [Kelly Criterion & Capital Allocation](#7-kelly-criterion--capital-allocation)

---

## 1. Executive Summary

This document specifies a systematic mathematical framework for identifying Expected Value (EV)
opportunities across global exchanges and sportsbooks.

The engine derives a high-fidelity Consensus Market Price from a hybrid basket of up to seven
primary data seats, operating on a single-outcome basis; no opposing outcome prices are
required. Signals are validated through a four-tier funnel: raw consensus probability, two
fixed-margin barriers, and a full overround normalisation as the most rigorous final tier.

The signal engine is built in Python and executed on command. All prices are collected at the
moment of execution. Capital deployment is governed by a Dynamic Fractional Kelly model that
scales stake size to signal quality, explicitly rewarding high-probability value over
speculative longshots carrying equivalent EV.

---

## 2. The Hybrid Consensus Basket

The model derives its source of truth from a 7-seat benchmark, combining efficient
price-discovery markets and a soft-market control index.

### 2.1 Basket Composition

| Seat       | Type               | Role                            | Access                        |
| :--------- | :----------------- | :------------------------------ | :---------------------------- |
| Betfair    | Exchange           | Primary price discovery         | Via OddsPapi (back + lay)     |
| Smarkets   | Exchange           | Secondary price discovery       | Direct API (pending approval) |
| Polymarket | Prediction Market  | Cross-market probability signal | Via OddsPapi                  |
| Kalshi     | Prediction Market  | Cross-market probability signal | Via OddsPapi                  |
| Pinnacle   | Sharp Bookmaker    | Sharpest fixed-odds reference   | Via OddsPapi                  |
| Bet365     | High-Fidelity Book | High-liquidity retail anchor    | Via OddsPapi                  |
| `S_idx`    | Soft Market Index  | Retail market control variable  | Via OddsPapi                  |

All basket seats except Smarkets are sourced from a single OddsPapi call per run.
Smarkets is accessed via direct API once approval is confirmed.

### 2.2 The Soft Market Index (`S_idx`)

`S_idx` is the mean implied probability across 17 major UK retail sportsbooks, sourced
from the OddsPapi feed.

$$S_{idx} = \frac{\sum_{i=1}^{N} IP_{soft_i}}{N}$$

The 17 books comprising `S_idx` are defined in `config.py`:

```
888sport, betmgm.co.uk, betway, bwin, casumo, coral, grosvenor, ladbrokes,
leovegas, lottoland, netbet, paddypower, pokerstars.uk, sportingbet,
unibet, virginbet, williamhill
```

`S_idx` functions as a control variable. Aggregating 17 books means it will closely reflect
the prevailing retail market average. Its role is to anchor the consensus against the retail
market; the sharp and exchange seats carry the directional signal weight.

### 2.3 Single-Outcome Architecture

The signal engine operates on a single-outcome basis. Only the target outcome's prices are
required across the basket; opposing outcome prices are not collected or used. This keeps the
data model simple and allows the engine to operate on markets where opposing prices are illiquid
or unavailable, e.g. player prop bets, shots on target, booking markets.

The overround normalisation model (M4) is the exception; it requires all outcome prices and
is treated as an optional enhancement tier applied where full market data is available.

### 2.4 Market Modules

Three dedicated analytics modules handle distinct market types, each calling the shared
data infrastructure layer (`core.py`):

| Module             | Market Type              | M4 Eligible |
| :----------------- | :----------------------- | :---------- |
| `match_odds_bot`   | Match result odds        | Yes         |
| `2up_bot`          | 2-Up promotion markets   | Yes         |
| `player_props_bot` | Player proposition bets  | No          |

`player_props_bot` operates in single-outcome mode only; M4 requires opposing outcome prices
which are not collected for player props markets.

---

## 3. Mathematical Glossary & Definitions

### 3.1 Implied Probability (`IP`)

$$IP = \frac{1}{D}$$

Where `D` is the decimal odds offered by a given seat.

Excel analogy: `=1/D2` where D2 contains the decimal odds.

Note: Kalshi and Polymarket return prices already in implied probability format (0-1 scale)
and do not require this conversion.

### 3.2 Consensus Implied Probability (`IP_bar`)

The mean `IP` across all active seats at the point of execution.

$$\overline{IP} = \frac{\sum_{i=1}^{N_{active}} IP_i}{N_{active}}$$

Active seats are those with an available price for the target outcome at execution time.
Seats without a price are excluded automatically; the consensus adjusts to however many
seats are live.

### 3.3 Total Overround (`Omega`) - M4 Only

The sum of consensus implied probabilities across every outcome in the market.

$$\Omega = \sum_{i=1}^{n} \overline{IP}_i$$

`Omega` is only required for Model 4. In a fair zero-margin market `Omega = 1.0`; in
practice `Omega > 1.0`, the excess above 1.0 being the bookmaker's margin. For all other
models, `IP_bar` alone is sufficient.

---

## 4. The Quad-Tier Model Logic

Every signal is evaluated against four independent models. The first three models operate on
`IP_bar` of the target outcome only. Model 4 requires full market data and is the most complex
tier; it is built last and treated as an optional enhancement.

A signal qualifies for a given tier only if `EV > 10%` for all required models at that tier.

---

### Model 1 - Raw Consensus (The Base Truth)

The direct mean of all active seat implied probabilities for the target outcome. No normalisation
or margin adjustment is applied; this is the purest available estimate of market consensus.

$$P_{M1} = \overline{IP}$$

---

### Model 2 - 7.5% Fixed Barrier (Sense Check A)

Applies a 7.5% discount to `IP_bar`, acting as the first margin buffer and accounting for
the bookmaker's embedded overround.

$$P_{M2} = \overline{IP} \times (1 - 0.075)$$

---

### Model 3 - 10% Fixed Barrier (Sense Check B)

Applies a harder 10% discount to `IP_bar`. A more conservative filter than M2; signals
surviving this model have demonstrated value against a meaningful margin assumption.

$$P_{M3} = \overline{IP} \times (1 - 0.10)$$

---

### Model 4 - Consensus Normalisation (Full Overround Strip) — Build Last

Requires the implied probabilities of all outcomes in the market. Strips the overround
proportionally to derive a true zero-margin probability for the target outcome.

$$P_{M4} = \frac{\overline{IP}}{\Omega}$$

Where `Omega` is the sum of `IP_bar` across all outcomes in the market.

This is the most data-intensive model in the framework. It is only viable on markets where
opposing outcome prices are available across a sufficient number of seats. It is marked as
the Elite tier because it represents the most rigorous normalisation; it is also the last
to be built. On markets where full data is unavailable, M4 is skipped and the signal tier
ceiling is Confirmed.

---

## 5. Expected Value & Signal Tiers

### 5.1 EV Formula

$$EV = (P_{model} \times D_{offered}) - 1$$

A positive `EV` means the offered odds imply a return greater than the model probability
warrants. For signal tier qualification, a minimum threshold of `EV > 10%` is required at
each model level; signals returning between `0%` and `10%` are calculated and recorded
but do not qualify for any tier.

### 5.2 Signal Tier Table

| Signal Tier   | Models Required | Description                                 |
| :------------ | :-------------- | :------------------------------------------ |
| **Standard**  | M1              | Value against raw consensus                 |
| **Buffered**  | M1, M2          | Value survives the 7.5% margin buffer       |
| **Confirmed** | M1, M2, M3      | Value survives the 10% margin buffer        |
| **Elite**     | M1, M2, M3, M4  | Value survives full overround normalisation |

When M4 data is unavailable, Confirmed is the maximum achievable tier.

---

## 6. Data Convergence & Signal Confidence

Basket agreement is measured using the coefficient of variation across all active seat IPs.

$$\text{CV} = \frac{\sigma_{IP}}{\overline{IP}}$$

Where `sigma_IP` is the standard deviation of all active seat implied probabilities.

Excel analogy: `=STDEV(range)/AVERAGE(range)` applied across all active seat IPs.

A CV of <= 10% indicates a well-converged basket. High variance across the basket, regardless
of signal tier, may indicate a market in motion or a suspended event. These signals are flagged
in output for manual review but are not discarded.

---

## 7. Kelly Criterion & Capital Allocation

### 7.1 Baseline Kelly

The baseline stake fraction `f*` optimises long-run bankroll growth relative to perceived edge.

$$f^* = \frac{(D_{offered} - 1) \times P_{adj} - (1 - P_{adj})}{D_{offered} - 1}$$

Where `P_adj` is the probability from the chosen model tier, typically `P_M2`.

### 7.2 Dynamic Confidence Multiplier

Instead of a fixed fraction, e.g. always 0.25 of Kelly, the system derives a multiplier
that scales linearly with the model's win probability.

$$L_{dynamic} = M \times P_{adj}$$

Where `M` is the Aggression Constant (recommended range: `0.5 - 1.0`).

Design principle: two signals with identical EV are not equally attractive. A higher implied
probability means lower variance and more reliable bankroll compounding; this framework
explicitly rewards that by allocating more capital to high-probability value than to
speculative longshots carrying the same edge.

### 7.3 Final Stake

$$f_{final} = f^* \times (M \times P_{adj})$$

`P_adj` does double duty in the framework; it drives the baseline Kelly fraction through
the EV calculation and then scales the final stake a second time through the dynamic
multiplier. Capital allocation decays non-linearly as probability falls.

#### Example Table (M = 1.0)

| `P_adj`          | Baseline `f*` | Multiplier `L` | Final `f_final` |
| :--------------- | :------------ | :------------- | :-------------- |
| 60% (high conf.) | 10.0%         | 0.60           | **6.00%**       |
| 25% (standard)   | 5.0%          | 0.25           | **1.25%**       |
| 5% (speculative) | 2.0%          | 0.05           | **0.10%**       |

### 7.4 Execution Guardrails

1. **Bankroll update frequency:** Refresh total bankroll every 24 hours.
2. **Liquid capital only:** Use liquid funds only; exclude capital locked in open positions.

### 7.5 Implementation Workflow

The following sequence describes the end-to-end execution path from raw odds ingestion to an
actionable output. Each step maps directly to a Python function in the signal engine module.
The engine is executed on command; all prices are collected at the point of execution.

**Step 1 — Odds Ingestion**
All basket seat prices except Smarkets are collected in a single OddsPapi call, returning
Betfair (back + lay), Pinnacle, Bet365, Kalshi, Polymarket and all S_idx soft books
simultaneously. Smarkets back and lay prices are collected via direct API. Seats with no
available price are excluded automatically from the basket.

**Step 2 — Implied Probability Conversion**
Convert each seat's decimal odds to implied probability using `IP = 1 / D`. Kalshi and
Polymarket prices are already in IP format and require no conversion. `S_idx` is computed
as the mean IP across all 17 active soft-market books before being treated as a single
basket seat.

**Step 3 — Consensus Basket Construction**
Compute `IP_bar` as the mean of all active seat IPs for the target outcome. Flag basket
variance using the coefficient of variation formula; any basket with CV > 10% is marked
for manual review but is not discarded.

**Step 4 — Model Calculation**
Compute `P_M1` through `P_M3` from `IP_bar` alone. Attempt `P_M4` only if opposing
outcome prices are available; otherwise skip and cap the signal tier at Confirmed.

**Step 5 — EV Calculation**
For each model, compute `EV = (P_model x D_offered) - 1`. All available model EVs are
recorded; a negative EV at any model does not suppress calculation of the remaining models.

**Step 6 — Signal Tier Assignment**
Assign the highest signal tier the outcome qualifies for, based on how many consecutive
models return `EV > 10%` starting from M1. Tiers are strictly sequential; a signal cannot
qualify for Confirmed without first passing Standard and Buffered. Any model returning
`EV < 10%` terminates the tier ladder at the tier below.

**Step 7 — Kelly Stake Calculation**
Using `P_adj` (default: `P_M2`), compute `f*`. Apply `L = M x P_adj` to derive `f_final`.
Multiply by current liquid bankroll to produce a currency stake amount.

**Step 8 — Output**
For each qualifying signal, write the following fields to a timestamped Excel file saved
to `outputs/`:

| Field              | Description                                      |
| :----------------- | :----------------------------------------------- |
| `event_id`         | Unique identifier for the market/event           |
| `outcome`          | The specific outcome the signal applies to       |
| `signal_tier`      | Standard / Buffered / Confirmed / Elite          |
| `ev_m1` — `ev_m4`  | EV value for each model                          |
| `p_adj`            | Probability used for staking (`P_M2` default)    |
| `d_offered`        | The decimal odds the signal is struck against    |
| `f_final`          | Final stake as a fraction of bankroll            |
| `stake_amount`     | Currency value of the stake                      |
| `basket_variance`  | CV flag for manual review if > 10%               |
| `active_seats`     | Number of seats that contributed to `IP_bar`     |
| `timestamp`        | Time of execution                                |

---