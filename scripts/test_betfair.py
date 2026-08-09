import betfairlightweight
from dotenv import load_dotenv
import os

load_dotenv()

API_KEY  = os.getenv("BETFAIR_API_KEY")
USERNAME = os.getenv("BETFAIR_USERNAME")
PASSWORD = os.getenv("BETFAIR_PASSWORD")

print(f"API Key loaded: {bool(API_KEY)}")
print(f"Username loaded: {bool(USERNAME)}")
print(f"Password loaded: {bool(PASSWORD)}")

# Build full path to certs folder
certs_path = os.path.join(os.getcwd(), "certs")
print(f"Certs path: {certs_path}")

client = betfairlightweight.APIClient(
    username=USERNAME,
    password=PASSWORD,
    app_key=API_KEY,
    certs=certs_path
)

client.login()
print("Login successful")

event_types = client.betting.list_event_types()
for et in event_types:
    print(et.event_type.id, et.event_type.name)