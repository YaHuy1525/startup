import os
import requests
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("YOUTUBE_CLIENT_ID")
client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
refresh_token = os.getenv("YOUTUBE_REFRESH_TOKEN")

print(f"Client ID: {client_id[:10]}...")
print(f"Client Secret: {client_secret[:5]}...")
print(f"Refresh Token: {refresh_token[:10]}...{refresh_token[-5:]}")

url = "https://oauth2.googleapis.com/token"
data = {
    "client_id": client_id,
    "client_secret": client_secret,
    "refresh_token": refresh_token,
    "grant_type": "refresh_token"
}

response = requests.post(url, data=data)
print("\nResponse Status:", response.status_code)
print("Response Body:", response.json())
