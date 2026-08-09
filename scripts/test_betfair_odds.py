import betfairlightweight
from betfairlightweight.filters import market_filter
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY  = os.getenv("BETFAIR_API_KEY")
USERNAME = os.getenv("BETFAIR_USERNAME")
PASSWORD = os.getenv("BETFAIR_PASSWORD")

certs_path = os.path.join(os.getcwd(), "certs")

# Login
client = betfairlightweight.APIClient(
    username=USERNAME,
    password=PASSWORD,
    app_key=API_KEY,
    certs=certs_path
)
client.login()
print("Login successful")

# Step 1 — Find Match Odds market for Mexico vs South Africa
markets = client.betting.list_market_catalogue(
    filter=market_filter(
        event_type_ids=["1"],
        text_query="Mexico v South Africa"
    ),
    market_projection=["RUNNER_DESCRIPTION", "EVENT"],
    max_results=10
)

# Filter to Match Odds only and build runner name lookup
match_odds_id = None
runner_names = {}

for market in markets:
    if market.market_name == "Match Odds":
        match_odds_id = market.market_id
        for runner in market.runners:
            runner_names[runner.selection_id] = runner.runner_name
        print(f"Match Odds market found — ID: {match_odds_id}")

if not match_odds_id:
    print("Match Odds market not found")
    exit()

# Step 2 — Get live prices
market_books = client.betting.list_market_book(
    market_ids=[match_odds_id],
    price_projection={"priceData": ["EX_BEST_OFFERS"]}
)

print("\n--- BETFAIR | Mexico vs South Africa | Match Odds ---")
for market_book in market_books:
    for runner in market_book.runners:
        name = runner_names.get(runner.selection_id, runner.selection_id)
        best_back = runner.ex.available_to_back
        if best_back:
            price = best_back[0].price
            print(f"  {name}: {price}")