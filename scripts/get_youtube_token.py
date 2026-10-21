"""BIR MARTA kompyuteringizda ishga tushiring: YouTube ruxsatini olib, refresh token beradi.

1) pip install google-auth-oauthlib
2) Google Cloud'dan yuklab olingan client_secret.json shu papkada bo'lsin
3) python get_youtube_token.py
Brauzer ochiladi -> UzBooks kanali bog'langan Google hisobini tanlang -> ruxsat bering.
Ekranda chiqqan 3 ta qiymatni GitHub Secrets'ga qo'ying.
"""
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube"]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
cfg = json.load(open("client_secret.json"))
cfg = cfg.get("installed") or cfg.get("web")
print("\n=== GitHub Secrets uchun ===")
print("YT_CLIENT_ID     =", cfg["client_id"])
print("YT_CLIENT_SECRET =", cfg["client_secret"])
print("YT_REFRESH_TOKEN =", creds.refresh_token)
