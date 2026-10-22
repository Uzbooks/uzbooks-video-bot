"""Barcha sozlamalar shu yerda. Maxfiy kalitlar faqat muhit o'zgaruvchilaridan
(GitHub Secrets) olinadi — kodga hech qachon yozilmaydi."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
STATE = ROOT / "state"
WORK = ROOT / "work"          # vaqtinchalik fayllar (gitga tushmaydi)
QUEUE_FILE = STATE / "queue.json"


def env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.environ.get(name) or default
    if required and not val:
        raise RuntimeError(f"Muhit o'zgaruvchisi topilmadi: {name}")
    return val or ""


# --- API kalitlar (GitHub Secrets) ---
GEMINI_API_KEY = lambda: env("GEMINI_API_KEY", required=True)
# ElevenLabs ixtiyoriy: kalit bo'lmasa, bepul Edge ovozi ishlatiladi
ELEVENLABS_API_KEY = lambda: env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = lambda: env("ELEVENLABS_VOICE_ID")
TELEGRAM_BOT_TOKEN = lambda: env("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_ADMIN_ID = lambda: env("TELEGRAM_ADMIN_ID", required=True)
YT_CLIENT_ID = lambda: env("YT_CLIENT_ID", required=True)
YT_CLIENT_SECRET = lambda: env("YT_CLIENT_SECRET", required=True)
YT_REFRESH_TOKEN = lambda: env("YT_REFRESH_TOKEN", required=True)

# --- Modellar (GitHub Variables orqali o'zgartirsa bo'ladi) ---
TEXT_MODEL = env("TEXT_MODEL", "gemini-3.8-flash")   # bepul tarifda ishlaydi
GEMINI_IMAGE_MODEL = env("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
ELEVENLABS_MODEL = env("ELEVENLABS_MODEL", "eleven_v3")
# Ovoz: "auto" (ElevenLabs kaliti bo'lsa u, bo'lmasa Edge), "elevenlabs" yoki "edge"
TTS_PROVIDER = env("TTS_PROVIDER", "auto")
EDGE_VOICE = env("EDGE_VOICE", "uz-UZ-SardorNeural")   # yoki uz-UZ-MadinaNeural
# Rasm: "auto" (Gemini, ishlamasa bepul dizayn-kartochka), "gemini" yoki "cards"
IMAGE_PROVIDER = env("IMAGE_PROVIDER", "auto")

# --- Video talablari ---
TARGET_MINUTES_MIN = 7.5
TARGET_MINUTES_MAX = 12.5
WORDS_MIN = 1000
WORDS_MAX = 1450
BLITZ_COUNT = 7
VIDEO_W, VIDEO_H = 1920, 1080
FPS = 25
CHANNEL_NAME = "UzBooks"
