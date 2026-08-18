# ladder.py
# True achievable lay pricing for 2upbotv2.
#
# THE PROBLEM THIS SOLVES
# ------------------------------------------------------------------
# v1 read the best lay price and assumed it held for the entire stake. It does
# not. A live example from 16 Aug 2026:
#
#     Marseille   lay 1.84   size available: 19.31
#
# Against a $100 back stake you need roughly $100 of lay stake. Only 19.31
# fills at 1.84; the rest fills at 1.9, 2.0 and worse, quietly pushing the
# real worst case well past MAX_LOSS. v1 would have reported the 1.84 number
# and called it qualifying.
#
# THE MATHS
# Back stake S at odds B. Lay stakes T_i at prices L_i.
#
#     If the selection WINS:   S(B - 1) - SUM T_i(L_i - 1)
#     If the selection LOSES:  -S + SUM T_i
#
# Setting those equal and simplifying gives one condition:
#
#     SUM (T_i x L_i) = S x B
#
# In words: the lay legs must buy exactly as much payout as the back bet
# would return. So we walk down the ladder buying payout until S x B is
# covered, cheapest price first.
#
# SANITY CHECK: with one price this reduces to T = S x B / L and a worst case
# of (B / L) - 1, which is exactly the formula v1 and config.py already use.
#
# Excel analogy: SUMPRODUCT(stakes, prices) must equal S x B. Fill that target
# from the cheapest rows down until it is met.
#
# Makes no API calls. Pure arithmetic.

import sys

# Floating-point comparisons need a tolerance. Money is counted to the penny,
# so anything under a tenth of a penny is treated as zero.
EPSILON = 0.001


def _clean_levels(ladder):
    """
    Keep only usable levels, in the order given.

    Betfair returns availableToLay best price first - that is, LOWEST price
    first, because a lower lay price is better for the layer. The order is
    preserved rather than re-sorted, so a malformed feed shows up as a bad
    result instead of being silently tidied away.
    """
    cleaned = []
    for level in (ladder or []):
        if not isinstance(level, dict):
            continue
        price = level.get("price")
        size = level.get("size")
        if not isinstance(price, (int, float)) or price <= 1.0:
            continue
        if not isinstance(size, (int, float)) or size <= 0:
            continue
        cleaned.append({"price": float(price), "size": float(size)})
    return cleaned


def top_of_book_worst_case(ladder, back_odds):
    """
    The number v1 reports: worst case using only the best lay price.

    Kept so v2's output can show both figures side by side and make the
    difference visible rather than theoretical.
    """
    levels = _clean_levels(ladder)
    if not levels:
        return None
    best = levels[0]["price"]
    return (back_odds / best) - 1.0


def achievable_lay(ladder, back_stake, back_odds):
    """
    Work out what laying the full stake would really cost.

    Returns a dict:
        filled              True if the ladder could cover the whole hedge
        lay_stake           total money laid across all levels
        effective_price     the single price equivalent to the fill
        worst_case          P&L as a fraction of back stake (negative = loss)
        liability           what the lay legs risk
        levels_used         how many depth levels were consumed
        breakdown           per-level stake and price actually taken
        top_of_book_price   best price, for comparison
        top_of_book_worst   worst case v1 would have reported
        shortfall_payout    payout still uncovered when the ladder ran out

    A dict rather than a bare number because the caller needs to know HOW the
    figure was reached - a worst case of -4% built from three levels and one
    built from a single deep level are not equally trustworthy.
    """
    levels = _clean_levels(ladder)

    result = {
        "filled": False,
        "lay_stake": 0.0,
        "effective_price": None,
        "worst_case": None,
        "liability": 0.0,
        "levels_used": 0,
        "breakdown": [],
        "top_of_book_price": levels[0]["price"] if levels else None,
        "top_of_book_worst": top_of_book_worst_case(ladder, back_odds),
        "shortfall_payout": None,
        "reason": "",
    }

    if not levels:
        result["reason"] = "no usable lay levels"
        return result

    if back_stake <= 0 or back_odds <= 1.0:
        result["reason"] = "invalid back stake or odds"
        return result

    # The payout the lay legs must buy between them.
    target_payout = back_stake * back_odds
    remaining = target_payout

    total_stake = 0.0
    achieved_payout = 0.0

    for level in levels:
        if remaining <= EPSILON:
            break

        price = level["price"]
        size = level["size"]

        # Payout available at this level, if we consumed all of it.
        payout_here = size * price
        take_payout = min(remaining, payout_here)
        stake_here = take_payout / price

        total_stake += stake_here
        achieved_payout += take_payout
        remaining -= take_payout

        result["breakdown"].append({
            "price": price,
            "stake": round(stake_here, 2),
            "payout": round(take_payout, 2),
            "size_available": size,
        })

    result["levels_used"] = len(result["breakdown"])
    result["lay_stake"] = round(total_stake, 2)
    result["liability"] = round(achieved_payout - total_stake, 2)

    if total_stake > 0:
        result["effective_price"] = round(achieved_payout / total_stake, 4)

    if remaining > EPSILON:
        # The visible ladder cannot cover the hedge. The worst case is not
        # meaningful here - part of the position would be unhedged - so it is
        # deliberately left as None rather than reported optimistically.
        result["filled"] = False
        result["shortfall_payout"] = round(remaining, 2)
        result["reason"] = (f"ladder exhausted - {remaining:.2f} of "
                            f"{target_payout:.2f} payout uncovered")
        return result

    result["filled"] = True
    result["worst_case"] = (total_stake / back_stake) - 1.0
    result["reason"] = "filled"
    return result


def qualifies(ladder, back_stake, back_odds, max_loss,
              require_full_fill=True):
    """
    Apply the threshold to a ladder-priced selection.

    Returns (qualified, result). The result dict is returned either way so a
    rejection can be logged with the numbers that caused it.
    """
    result = achievable_lay(ladder, back_stake, back_odds)

    if not result["filled"]:
        if require_full_fill:
            return False, result
        return False, result

    return result["worst_case"] >= max_loss, result


# =============================================================
# SELF-TEST
# =============================================================


def run_tests():
    """Prove the arithmetic before any money depends on it."""
    checks = 0
    failures = []

    def check(label, condition):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    def close(a, b, tol=0.005):
        return a is not None and abs(a - b) <= tol

    # --- 1. Deep single level reduces to the v1 formula ---
    deep = [{"price": 2.0, "size": 10000.0}]
    r = achievable_lay(deep, 100.0, 2.0)
    check("deep book fills", r["filled"])
    check("deep book lay stake = 100", close(r["lay_stake"], 100.0))
    check("deep book worst case = 0", close(r["worst_case"], 0.0))
    check("deep book uses 1 level", r["levels_used"] == 1)

    # --- 2. Back shorter than lay is a locked-in profit (true arbitrage) ---
    r = achievable_lay([{"price": 3.45, "size": 10000.0}], 100.0, 3.50)
    check("arb worst case positive", r["worst_case"] > 0)
    check("arb matches B/L - 1", close(r["worst_case"], (3.50 / 3.45) - 1))

    # --- 3. THE MARSEILLE CASE - thin top of book ---
    # Best price 1.84 with only 19.31 behind it, then worse levels.
    thin = [
        {"price": 1.84, "size": 19.31},
        {"price": 1.90, "size": 50.00},
        {"price": 2.00, "size": 500.00},
    ]
    r = achievable_lay(thin, 100.0, 1.80)
    check("thin book fills", r["filled"])
    check("thin book uses 3 levels", r["levels_used"] == 3)
    # Top of book flatters the result badly.
    check("top of book looks better",
          r["top_of_book_worst"] > r["worst_case"])
    check("top of book near -2.2%", close(r["top_of_book_worst"], -0.0217))
    check("true worst case near -6.0%", close(r["worst_case"], -0.0595, 0.002))
    # And that is the difference between qualifying and not.
    ok_true, _ = qualifies(thin, 100.0, 1.80, -0.05)
    check("thin book REJECTED on true price", not ok_true)

    # --- 4. Payout identity holds: SUM(stake x price) = S x B ---
    total_payout = sum(row["payout"] for row in r["breakdown"])
    check("payout identity", close(total_payout, 100.0 * 1.80, 0.05))

    # --- 5. Effective price sits between best and worst level used ---
    check("effective price above best",
          r["effective_price"] > thin[0]["price"])
    check("effective price below worst used",
          r["effective_price"] < thin[2]["price"])

    # --- 6. Shallow ladder that cannot fill at all ---
    shallow = [{"price": 2.0, "size": 5.0}]
    r = achievable_lay(shallow, 100.0, 2.0)
    check("shallow book not filled", not r["filled"])
    check("shallow worst case is None", r["worst_case"] is None)
    check("shallow reports shortfall", r["shortfall_payout"] > 0)
    ok, _ = qualifies(shallow, 100.0, 2.0, -0.05, require_full_fill=True)
    check("shallow book rejected", not ok)

    # --- 7. Rubbish input is refused, not guessed at ---
    for bad in (None, [], [{"price": None, "size": 10}],
                [{"price": 2.0, "size": 0}], [{"price": 1.0, "size": 50}]):
        r = achievable_lay(bad, 100.0, 2.0)
        check(f"bad ladder refused: {bad}", not r["filled"])

    r = achievable_lay(deep, 0.0, 2.0)
    check("zero stake refused", not r["filled"])
    r = achievable_lay(deep, 100.0, 1.0)
    check("odds of 1.0 refused", not r["filled"])

    # --- 8. More depth is never worse than less ---
    two_levels = achievable_lay(thin[:2] + [{"price": 2.0, "size": 500.0}],
                                100.0, 1.80)
    one_deep = achievable_lay([{"price": 1.84, "size": 500.0}], 100.0, 1.80)
    check("a deep top of book beats a thin one",
          one_deep["worst_case"] > two_levels["worst_case"])

    return checks, failures


if __name__ == "__main__":
    print("=" * 70)
    print("ladder.py SELF-TEST (no API requests)")
    print("=" * 70)

    checks, failures = run_tests()

    for failure in failures:
        print(f"  FAIL  {failure}")

    # Show the Marseille case in full - it is the argument for v2.
    thin = [
        {"price": 1.84, "size": 19.31},
        {"price": 1.90, "size": 50.00},
        {"price": 2.00, "size": 500.00},
    ]
    result = achievable_lay(thin, 100.0, 1.80)

    print("\nWORKED EXAMPLE - back $100 at 1.80, thin lay ladder")
    print("-" * 70)
    for row in result["breakdown"]:
        print(f"  lay {row['stake']:>7.2f} at {row['price']:<6} "
              f"(size available {row['size_available']}) "
              f"-> payout {row['payout']:.2f}")
    print(f"  Total lay stake:      {result['lay_stake']:.2f}")
    print(f"  Effective lay price:  {result['effective_price']}")
    print(f"  Liability:            {result['liability']:.2f}")
    print("")
    print(f"  v1 would report:      {result['top_of_book_worst']:+.2%} "
          f"(top of book, 1.84)")
    print(f"  v2 true worst case:   {result['worst_case']:+.2%}")
    print(f"  Against MAX_LOSS -5%: "
          f"{'QUALIFIES' if result['worst_case'] >= -0.05 else 'REJECTED'}")

    print("\n" + "=" * 70)
    if failures:
        print(f"TESTS FAILED - {len(failures)} of {checks} checks failed")
        print("=" * 70)
        sys.exit(1)

    print(f"LADDER TESTS PASSED - {checks} checks")
    print("=" * 70)