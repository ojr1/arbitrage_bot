import requests

BASE_URL = "https://gamma-api.polymarket.com"

# Search specifically for World Cup match markets
response = requests.get(
    f"{BASE_URL}/markets",
    params={
        "active": "true",
        "limit": 20,
        "order": "volume24hr",
        "ascending": "false"
    }
)

print("--- WORLD CUP MARKETS ON POLYMARKET ---")
for market in response.json():
    question = market.get("question", "")
    if "world cup" in question.lower() or "fifa" in question.lower():
        print(question, "| Price:", market.get("outcomePrices"))