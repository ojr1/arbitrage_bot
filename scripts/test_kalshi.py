import requests

BASE_URL = "https://external-api.kalshi.com/trade-api/v2"

# Get World Cup events
events_response = requests.get(
    f"{BASE_URL}/events",
    params={
        "series_ticker": "KXWCGAME",
        "status": "open",
        "limit": 5,
        "with_nested_markets": "true"
    }
)

events = events_response.json().get("events", [])

for event in events:
    print(f"\n--- {event.get('title')} ---")
    markets = event.get("markets", [])
    for market in markets:
        title = market.get("yes_sub_title") or market.get("title", "")
        yes_price = market.get("yes_ask_dollars")
        print(f"  {title}: Yes {yes_price}")