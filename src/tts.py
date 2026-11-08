"""O'zbekcha ovoz — tashqi interfeys (main.py shu fayldan foydalanadi).

Dvijoklar src/tts_engines/ ichida: Edge (bepul), ElevenLabs (pullik), OmniVoice (bepul, lokal).
Tanlash: TTS_PROVIDER, zaxira: TTS_FALLBACK (GitHub Variables).
"""
from pathlib import Path

from . import tts_engines
from .tts_engines import END_PAD, TTSError, sentences  # noqa: F401  (eski importlar uchun)
from .tts_engines.base import duration  # noqa: F401


def provider() -> str:
    """Tanlangan asosiy dvijok nomi (masalan "edge")."""
    return tts_engines.primary_name()


def voice_label() -> str:
    """Haqiqatda ishlatilgan dvijok va ovoz (zaxiraga o'tilgan bo'lsa — zaxiraniki)."""
    return tts_engines.last_label or provider()


def warnings() -> list[str]:
    return list(tts_engines.warnings)


def synthesize_sections(texts: list[str], dests: list[Path]) -> list[tuple[float, list]]:
    """Barcha bo'limlar: [(davomiylik, [(boshlanish, tugash, gap), ...]), ...]"""
    return tts_engines.synthesize_sections(texts, dests)


def synthesize_with_cues(text: str, dest: Path) -> tuple[float, list[tuple[float, float, str]]]:
    """Bitta bo'lim (eski interfeys). Yangi kod synthesize_sections() dan foydalanadi."""
    return tts_engines.synthesize_sections([text], [dest])[0]
