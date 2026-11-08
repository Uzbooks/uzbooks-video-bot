"""Barcha sozlamalar shu yerda. Maxfiy kalitlar faqat muhit o'zgaruvchilaridan
(GitHub Secrets) olinadi — kodga hech qachon yozilmaydi."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
STATE = ROOT / "state"
WORK = ROOT / "work"          # vaqtinchalik fayllar (gitga tushmaydi)
QUEUE_FILE = STATE / "queue.json"


def prompt(name: str) -> str:
    """prompts/ papkasidagi faylni o'qiydi; fayl yo'q bo'lsa, kod ichidagi zaxira matnni beradi."""
    path = PROMPTS / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    from .default_prompts import DEFAULTS
    print(f"  Ogohlantirish: prompts/{name} topilmadi, standart matn ishlatildi")
    return DEFAULTS.get(name, "")


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
# Pexels ixtiyoriy (bepul): bo'lsa, rasmlar o'rniga haqiqiy stok videolar qo'yiladi
PEXELS_API_KEY = lambda: env("PEXELS_API_KEY")
PIXABAY_API_KEY = lambda: env("PIXABAY_API_KEY")   # Pexels o'rniga yoki qo'shimcha
TELEGRAM_BOT_TOKEN = lambda: env("TELEGRAM_BOT_TOKEN", required=True)
TELEGRAM_ADMIN_ID = lambda: env("TELEGRAM_ADMIN_ID", required=True)
YT_CLIENT_ID = lambda: env("YT_CLIENT_ID", required=True)
YT_CLIENT_SECRET = lambda: env("YT_CLIENT_SECRET", required=True)
YT_REFRESH_TOKEN = lambda: env("YT_REFRESH_TOKEN", required=True)

# --- Modellar (GitHub Variables orqali o'zgartirsa bo'ladi) ---
# Bo'sh qolsa, kalitingiz uchun mavjud Gemini Flash modellari avtomatik topiladi
TEXT_MODEL = env("TEXT_MODEL", "")
# Qo'shimcha zaxira modellar (vergul bilan); odatda kerak emas
TEXT_MODEL_FALLBACKS = env("TEXT_MODEL_FALLBACKS", "")
GEMINI_IMAGE_MODEL = env("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
ELEVENLABS_MODEL = env("ELEVENLABS_MODEL", "eleven_v3")
# Ovoz: "auto" (ElevenLabs kaliti bo'lsa u, bo'lmasa Edge), "elevenlabs", "edge" yoki "omnivoice"
TTS_PROVIDER = env("TTS_PROVIDER", "auto")
# Asosiy ovoz ishlamasa, butun ovoz shu dvijok bilan qayta yoziladi ("none" — zaxirasiz)
TTS_FALLBACK = env("TTS_FALLBACK", "edge")
TTS_TIMEOUT = float(env("TTS_TIMEOUT", "180"))      # bitta so'rovni kutish chegarasi (soniya)
# Sonlarni so'z bilan yozish: "auto" (faqat OmniVoice uchun), "on" yoki "off"
TTS_NORMALIZE = env("TTS_NORMALIZE", "auto")
TTS_LOUDNESS = env("TTS_LOUDNESS", "-16")           # ovoz balandligi, LUFS (YouTube uchun -14..-16)
EDGE_VOICE = env("EDGE_VOICE", "uz-UZ-SardorNeural")   # yoki uz-UZ-MadinaNeural
# OmniVoice (bepul, lokal, CPU) — sinov bosqichida
OMNIVOICE_MODEL = env("OMNIVOICE_MODEL", "k2-fsa/OmniVoice")
OMNIVOICE_VOICE = env("OMNIVOICE_VOICE", "male, middle-aged, low pitch")   # ovoz tavsifi (inglizcha)
OMNIVOICE_STEPS = int(env("OMNIVOICE_STEPS", "32"))         # 16 — tezroq, 32 — sifatliroq
OMNIVOICE_MAX_MINUTES = float(env("OMNIVOICE_MAX_MINUTES", "150"))
OMNIVOICE_CACHE_DIR = env("OMNIVOICE_CACHE_DIR", str(Path.home() / ".cache" / "uzbooks"))   # saqlangan ovozlar
OMNIVOICE_REF_WAV = env("OMNIVOICE_REF_WAV")    # faqat lokal: o'z ovozingiz namunasi (repoga qo'ymang!)
OMNIVOICE_REF_TEXT = env("OMNIVOICE_REF_TEXT")
# Rasm: "auto" (Gemini, ishlamasa bepul dizayn-kartochka), "gemini" yoki "cards"
IMAGE_PROVIDER = env("IMAGE_PROVIDER", "auto")
# Sahna vizuali: "images" — har bir sahnaga mazmunga mos AI rasm (tavsiya, Gemini billing kerak),
# "stock" — avval Pixabay/Pexels stok video, topilmasa AI rasm
VISUAL_MODE = env("VISUAL_MODE", "images")
MAX_AI_IMAGES = int(env("MAX_AI_IMAGES", "70"))   # bitta videoga eng ko'p AI rasm (xarajat chegarasi)

# --- Video talablari ---
TARGET_MINUTES_MIN = 7.5
TARGET_MINUTES_MAX = 12.5
WORDS_MIN = 1000
WORDS_MAX = 1450
BLITZ_COUNT = 7
SCENE_SECONDS = 10.0    # bitta sahnaning taxminiy uzunligi (har bir bo'limda bir nechta sahna)
VIDEO_W, VIDEO_H = 1920, 1080
FPS = 25
CHANNEL_NAME = "UzBooks"
