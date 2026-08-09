import requests
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("ODDSPAPI_API_KEY")
BASE_URL = "https://api.oddspapi.io/v4"

# Get all bookmaker odds for Mexico vs South Africa
response = requests.get(
    f"{BASE_URL}/odds",
    params={
        "apiKey": API_KEY,
        "fixtureId": "id1000001666456904"
    }
)

data = response.json()
bookmakers = data.get("bookmakerOdds", {})

print(f"Total bookmakers returned: {len(bookmakers)}")
print("\n--- ALL BOOKMAKER SLUGS ---")
for slug in sorted(bookmakers.keys()):
    print(slug)