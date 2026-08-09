import requests
import os
import json
import time
import statistics
from datetime import datetime
from dotenv import load_dotenv
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from config import (
    SEAT_BET365, SEAT_PINNACLE, SEAT_BETFAIR,
    SEAT_KALSHI, SEAT_POLYMARKET,
    IP_FORMAT_SEATS, S_IDX_BOOKS, VARIANCE_LIMIT
)

load_dotenv()
API_KEY  = os.getenv("ODDSPAPI_API_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

TOURNAMENT_ID = 16
MARKET_ID     = "101"
OUTCOME_MAP   = {"101": "home", "102": "draw", "103": "away"}


# ─────────────────────────────────────────────
# HELPER: Extract price from one bookmaker block
# ─────────────────────────────────────────────

def _extract_price(bookmaker_data, outcome_id):
    try:
        markets = bookmaker_data.get("markets", {})
        if MARKET_ID not in markets:
            return None
        outcome  = markets[MARKET_ID]["outcomes"].get(outcome_id)
        if not outcome:
            return None
        player   = outcome["players"]["0"]
        exchange = player.get("exchangeMeta", {})
        if isinstance(exchange, dict) and exchange.get("back"):
            return exchange["back"][0].get("price")
        return player.get("price")
    except (KeyError, TypeError, IndexError):
        return None


# ─────────────────────────────────────────────
# IP CONVERSION
# ─────────────────────────────────────────────

def convert_to_ip(price, seat_slug):
    if price is None:
        return None
    try:
        if seat_slug in IP_FORMAT_SEATS:
            return float(price)
        return 1 / float(price)
    except (ZeroDivisionError, TypeError, ValueError):
        return None


# ─────────────────────────────────────────────
# S_IDX COMPUTATION
# ─────────────────────────────────────────────

def compute_s_idx(bookmaker_odds, outcome_id):
    ips = []
    for slug in S_IDX_BOOKS:
        if slug not in bookmaker_odds:
            continue
        price = _extract_price(bookmaker_odds[slug], outcome_id)
        ip    = convert_to_ip(price, slug)
        if ip is not None:
            ips.append(ip)
    if len(ips) < 3:
        return None
    return {"ip": sum(ips) / len(ips), "active_books": len(ips)}


# ─────────────────────────────────────────────
# BASKET VARIANCE
# ─────────────────────────────────────────────

def compute_basket_variance(seat_ips):
    if len(seat_ips) < 2:
        return {"cv": None, "flagged": False}
    values  = list(seat_ips.values())
    mean    = sum(values) / len(values)
    std_dev = statistics.stdev(values)
    cv      = std_dev / mean if mean else None
    flagged = cv > VARIANCE_LIMIT if cv else False
    return {"cv": round(cv, 4) if cv else None, "flagged": flagged}


# ─────────────────────────────────────────────
# FETCH ODDSPAPI
# ─────────────────────────────────────────────

def fetch_oddspapi():
    fixtures_response = requests.get(
        f"{BASE_URL}/fixtures",
        params={"apiKey": API_KEY, "tournamentId": TOURNAMENT_ID}
    )
    fixture_names = {}
    for f in fixtures_response.json():
        fixture_names[f["fixtureId"]] = {
            "home": f["participant1Name"],
            "away": f["participant2Name"]
        }

    all_books = [
        SEAT_BET365, SEAT_PINNACLE, SEAT_BETFAIR,
        SEAT_KALSHI, SEAT_POLYMARKET,
    ] + S_IDX_BOOKS

    combined = {}

    for book in all_books:
        response = requests.get(
            f"{BASE_URL}/odds-by-tournaments",
            params={
                "apiKey":        API_KEY,
                "tournamentIds": TOURNAMENT_ID,
                "bookmaker":     book
            }
        )
        data = response.json()

        if isinstance(data, dict) and "error" in data:
            print(f"  Skipping {book}: {data['error']['message']}")
            time.sleep(1.0)
            continue

        for fixture in data:
            fid = fixture.get("fixtureId")
            if not fid:
                continue
            if fid not in combined:
                combined[fid] = {"fixtureId": fid, "bookmakerOdds": {}}
            combined[fid]["bookmakerOdds"].update(fixture.get("bookmakerOdds", {}))

        print(f"  Fetched {book} ✓")
        time.sleep(1.0)

    raw_data = list(combined.values())

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path  = os.path.join("data", "raw", f"oddspapi_{timestamp}.json")
    with open(raw_path, "w") as f:
        json.dump(raw_data, f)

    print(f"\nTotal fixtures fetched: {len(raw_data)}")
    return raw_data, fixture_names


# ─────────────────────────────────────────────
# BUILD BASKET
# ─────────────────────────────────────────────

def build_basket():
    raw_data, fixture_names = fetch_oddspapi()

    named_seats = {
        "bet365":     SEAT_BET365,
        "pinnacle":   SEAT_PINNACLE,
        "betfair":    SEAT_BETFAIR,
        "kalshi":     SEAT_KALSHI,
        "polymarket": SEAT_POLYMARKET,
    }

    results = []

    for fixture in raw_data:
        fid   = fixture.get("fixtureId")
        names = fixture_names.get(fid, {})
        books = fixture.get("bookmakerOdds", {})

        fixture_result = {
            "fixture_id": fid,
            "home_team":  names.get("home", "Unknown"),
            "away_team":  names.get("away", "Unknown"),
        }

        for outcome_id, outcome_label in OUTCOME_MAP.items():
            seat_ips = {}

            for seat_name, slug in named_seats.items():
                if slug not in books:
                    continue
                price = _extract_price(books[slug], outcome_id)
                ip    = convert_to_ip(price, slug)
                if ip is not None:
                    seat_ips[seat_name] = round(ip, 6)

            s_idx = compute_s_idx(books, outcome_id)
            if s_idx:
                seat_ips["s_idx"] = round(s_idx["ip"], 6)

            active_ips = list(seat_ips.values())
            ip_bar     = sum(active_ips) / len(active_ips) if active_ips else None
            variance   = compute_basket_variance(seat_ips)

            fixture_result[outcome_label] = {
                "ip_bar":       round(ip_bar, 6) if ip_bar else None,
                "active_seats": len(active_ips),
                "cv":           variance["cv"],
                "cv_flagged":   variance["flagged"],
                "seats":        seat_ips
            }

        results.append(fixture_result)

    return results


# ─────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────

def export_to_excel(basket):
    """
    Export basket data to a formatted Excel file in outputs/.
    One row per fixture. Columns grouped by: Consensus | Bet365 | Pinnacle |
    Betfair | Kalshi | Polymarket | S_idx.
    Decimal odds shown for each seat. IP_bar shown as percentage.
    CV-flagged rows highlighted in yellow.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Basket"

    # ── Styles ──
    HEADER_FONT    = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    HEADER_FILL    = PatternFill("solid", start_color="1F4E79")
    GROUP_FILLS    = {
        "consensus":  PatternFill("solid", start_color="2E75B6"),
        "bet365":     PatternFill("solid", start_color="375623"),
        "pinnacle":   PatternFill("solid", start_color="833C00"),
        "betfair":    PatternFill("solid", start_color="7030A0"),
        "kalshi":     PatternFill("solid", start_color="C55A11"),
        "polymarket": PatternFill("solid", start_color="006064"),
        "s_idx":      PatternFill("solid", start_color="1F4E79"),
    }
    DATA_FONT      = Font(name="Arial", size=10)
    FLAG_FILL      = PatternFill("solid", start_color="FFEB3B")
    CENTER         = Alignment(horizontal="center", vertical="center")
    THIN           = Side(style="thin", color="D0D0D0")
    BORDER         = Border(left=THIN, right=THIN, bottom=THIN)

    seats          = ["bet365", "pinnacle", "betfair", "kalshi", "polymarket", "s_idx"]
    outcomes       = ["home", "draw", "away"]
    outcome_labels = {"home": "H", "draw": "D", "away": "A"}

    # ── Row 1: Group headers ──
    ws.row_dimensions[1].height = 18
    ws.row_dimensions[2].height = 18

    col = 1

    # Fixture column — spans rows 1 and 2
    ws.cell(1, col, "Fixture")
    ws.cell(1, col).font       = Font(name="Arial", bold=True, color="FFFFFF", size=10)
    ws.cell(1, col).fill       = HEADER_FILL
    ws.cell(1, col).alignment  = CENTER
    ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
    ws.column_dimensions[get_column_letter(col)].width = 28
    col += 1

    # Consensus group (IP_bar H/D/A + CV H/D/A)
    consensus_start = col
    for o in outcomes:
        ws.cell(1, col, f"IP_bar {outcome_labels[o]}")
        ws.cell(1, col).font      = HEADER_FONT
        ws.cell(1, col).fill      = GROUP_FILLS["consensus"]
        ws.cell(1, col).alignment = CENTER
        ws.column_dimensions[get_column_letter(col)].width = 11
        col += 1
    for o in outcomes:
        ws.cell(1, col, f"CV {outcome_labels[o]}")
        ws.cell(1, col).font      = HEADER_FONT
        ws.cell(1, col).fill      = GROUP_FILLS["consensus"]
        ws.cell(1, col).alignment = CENTER
        ws.column_dimensions[get_column_letter(col)].width = 9
        col += 1

    # Per-seat groups (H/D/A decimal odds)
    for seat in seats:
        seat_start = col
        for o in outcomes:
            label = f"{seat.title()} {outcome_labels[o]}"
            ws.cell(1, col, label)
            ws.cell(1, col).font      = HEADER_FONT
            ws.cell(1, col).fill      = GROUP_FILLS.get(seat, HEADER_FILL)
            ws.cell(1, col).alignment = CENTER
            ws.column_dimensions[get_column_letter(col)].width = 11
            col += 1

    # ── Data rows ──
    for row_idx, fixture in enumerate(basket, start=3):
        home = fixture["home_team"]
        away = fixture["away_team"]
        c    = 1

        # Check if any outcome is CV flagged
        any_flagged = any(
            fixture.get(o, {}).get("cv_flagged", False) for o in outcomes
        )
        row_fill = FLAG_FILL if any_flagged else None

        # Fixture name
        ws.cell(row_idx, c, f"{home} vs {away}")
        ws.cell(row_idx, c).font      = Font(name="Arial", bold=True, size=10)
        ws.cell(row_idx, c).alignment = Alignment(horizontal="left", vertical="center")
        if row_fill:
            ws.cell(row_idx, c).fill = row_fill
        c += 1

        # IP_bar per outcome (as %)
        for o in outcomes:
            ip_bar = fixture.get(o, {}).get("ip_bar")
            val    = round(ip_bar * 100, 2) if ip_bar else None
            ws.cell(row_idx, c, val)
            ws.cell(row_idx, c).font      = DATA_FONT
            ws.cell(row_idx, c).alignment = CENTER
            ws.cell(row_idx, c).number_format = "0.00%"
            ws.cell(row_idx, c, ip_bar)
            ws.cell(row_idx, c).number_format = "0.00%"
            if row_fill:
                ws.cell(row_idx, c).fill = row_fill
            c += 1

        # CV per outcome
        for o in outcomes:
            cv  = fixture.get(o, {}).get("cv")
            flg = fixture.get(o, {}).get("cv_flagged", False)
            ws.cell(row_idx, c, cv)
            ws.cell(row_idx, c).font          = DATA_FONT
            ws.cell(row_idx, c).alignment     = CENTER
            ws.cell(row_idx, c).number_format = "0.0000"
            if flg:
                ws.cell(row_idx, c).fill = FLAG_FILL
            c += 1

        # Per-seat decimal odds (1/IP)
        for seat in seats:
            for o in outcomes:
                ip  = fixture.get(o, {}).get("seats", {}).get(seat)
                val = round(1 / ip, 2) if ip else None
                ws.cell(row_idx, c, val)
                ws.cell(row_idx, c).font          = DATA_FONT
                ws.cell(row_idx, c).alignment     = CENTER
                ws.cell(row_idx, c).number_format = "0.00"
                if row_fill:
                    ws.cell(row_idx, c).fill = row_fill
                c += 1

    # Freeze header rows and fixture column
    ws.freeze_panes = "B3"

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path      = os.path.join("outputs", f"basket_{timestamp}.xlsx")
    wb.save(path)
    print(f"\nExcel file saved: {path}")
    return path


# ─────────────────────────────────────────────
# TEST BLOCK
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("Building basket...\n")
    basket = build_basket()

    print("\n--- BASKET OUTPUT (first 3 fixtures) ---")
    for fixture in basket[:3]:
        print(f"\n{fixture['home_team']} vs {fixture['away_team']}")
        for outcome in ["home", "draw", "away"]:
            if outcome in fixture:
                data = fixture[outcome]
                print(f"  {outcome.upper()}")
                print(f"    IP_bar:       {data['ip_bar']}")
                print(f"    Active seats: {data['active_seats']}")
                print(f"    CV:           {data['cv']} {'⚠ flagged' if data['cv_flagged'] else ''}")
                print(f"    Seat IPs:     {data['seats']}")

    print("\nExporting to Excel...")
    export_to_excel(basket)