import requests
from dotenv import load_dotenv
import os

load_dotenv()
API_KEY = os.getenv("ODDSPAPI_API_KEY")

BASE_URL = "https://api.oddspapi.io/v4"

response = requests.get(
    f"{BASE_URL}/sports",
    params={"apiKey": API_KEY}
)

print(f"Status code: {response.status_code}")
print(response.json())