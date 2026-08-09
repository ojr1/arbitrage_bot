import requests
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("ODDSPAPI_API_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

# Call 1 — Get fixture names (tournamentId 16 = World Cup)
fixtures_response = requests.get(
    f"{BASE_URL}/fixtures",
    params={"apiKey": API_KEY, "tournamentId": 16}
)

# Build a lookup dictionary: fixtureId -> team names
fixture_names = {}
for f in fixtures_response.json():
    fixture_names[f["fixtureId"]] = {
        "home": f["participant1Name"],
        "away": f["participant2Name"]
    }

# Call 2 — Get Bet365 odds for all World Cup fixtures
odds_response = requests.get(
    f"{BASE_URL}/odds-by-tournaments",
    params={"apiKey": API_KEY, "tournamentIds": 16, "bookmaker": "bet365"}
)

label_map = {"101": "Home", "102": "Draw", "103": "Away"}

for fixture in odds_response.json():
    fid = fixture.get("fixtureId")
    names = fixture_names.get(fid, {"home": "?", "away": "?"})
    bookmaker_odds = fixture.get("bookmakerOdds", {})

    if "bet365" in bookmaker_odds:
        markets = bookmaker_odds["bet365"].get("markets", {})
        if "101" in markets:
            outcomes = markets["101"]["outcomes"]
            print(f"\n--- {names['home']} vs {names['away']} ---")
            for outcome_id, outcome_data in outcomes.items():
                label = label_map.get(outcome_id, outcome_id)
                price = outcome_data["players"]["0"]["price"]
                print(f"  {label}: {price}")