"""Ovoz dvijoklari menejeri — bitta interfeys, avtomatik zaxira (fallback).

TTS_PROVIDER = auto | edge | aisha | elevenlabs | omnivoice
  auto  — ElevenLabs kaliti bo'lsa ElevenLabs, Aisha kaliti bo'lsa Aisha, bo'lmasa Edge
TTS_FALLBACK = edge (standart) | omnivoice | elevenlabs | none

Asosiy dvijok biror bo'limda yiqilsa, BUTUN ovoz zaxira dvijok bilan qaytadan yoziladi —
bitta videoda ikki xil ovoz aralashmaydi. Bu haqda ogohlantirish Telegram hisobotiga tushadi.
"""
import os
import re
import subprocess
import time
from pathlib import Path

from .. import audio_qa, config, uz_text
from .base import Engine, TTSError, duration

PROVIDERS = ("edge", "aisha", "elevenlabs", "omnivoice")
END_PAD = 0.7                       # bo'lim oxiridagi pauza (soniya)

warnings: list[str] = []           # oxirgi ishga tushirishdagi ogohlantirishlar
last_label = ""                     # haqiqatda ishlatilgan dvijok
_engines: dict[str, Engine] = {}


def _redact(msg: str) -> str:
    for name in ("ELEVENLABS_API_KEY", "AISHA_API_KEY", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN",
                 "PEXELS_API_KEY", "PIXABAY_API_KEY", "ELEVENLABS_VOICE_ID"):
        val = os.environ.get(name)
        if val and len(val) > 6:
            msg = msg.replace(val, "***")
    return msg


def make(name: str, voice: str = "") -> Engine:
    if name == "edge":
        from .edge import EdgeEngine
        return EdgeEngine(voice or config.EDGE_VOICE, timeout=config.TTS_TIMEOUT,
                          apostrophe=config.EDGE_APOSTROPHE)
    if name == "aisha":
        from .aisha import AishaEngine
        return AishaEngine(config.AISHA_API_KEY(), config.AISHA_MODEL, config.AISHA_MOOD, config.AISHA_SPEED,
                           voice or config.AISHA_VOICE_ID, timeout=config.TTS_TIMEOUT)
    if name == "elevenlabs":
        from .elevenlabs import ElevenLabsEngine
        return ElevenLabsEngine(config.ELEVENLABS_API_KEY(), voice or config.ELEVENLABS_VOICE_ID(),
                                config.ELEVENLABS_MODEL, config.env("ELEVENLABS_STABILITY"),
                                timeout=max(config.TTS_TIMEOUT, 300))
    if name == "omnivoice":
        from .omnivoice import OmniVoiceEngine
        return OmniVoiceEngine(voice or config.OMNIVOICE_VOICE, config.OMNIVOICE_MODEL,
                               config.OMNIVOICE_STEPS, config.OMNIVOICE_MAX_MINUTES,
                               Path(config.OMNIVOICE_CACHE_DIR), config.OMNIVOICE_REF_WAV,
                               config.OMNIVOICE_REF_TEXT)
    raise TTSError(f"Noma'lum ovoz dvijoki: {name}")


def engine(name: str) -> Engine:
    if name not in _engines:
        _engines[name] = make(name)
    return _engines[name]


def primary_name() -> str:
    p = (config.TTS_PROVIDER or "auto").strip().lower()
    if p == "auto":
        if config.ELEVENLABS_API_KEY() and config.ELEVENLABS_VOICE_ID():
            return "elevenlabs"
        return "aisha" if config.AISHA_API_KEY() else "edge"
    if p not in PROVIDERS:
        msg = f"TTS_PROVIDER='{p}' noto'g'ri (mumkin: auto, {', '.join(PROVIDERS)}) — Edge ishlatildi"
        print(f"  ⚠️ {msg}")
        if msg not in warnings:
            warnings.append(msg)
        return "edge"
    return p


def chain() -> list[str]:
    names = [primary_name()]
    fb = (config.TTS_FALLBACK or "edge").strip().lower()
    if fb not in ("none", "", *names):
        if fb in PROVIDERS:
            names.append(fb)
        else:
            warnings.append(f"TTS_FALLBACK='{fb}' noto'g'ri — zaxira sifatida Edge ishlatildi")
            if "edge" not in names:
                names.append("edge")
    return names


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _normalize_numbers(eng: Engine) -> bool:
    """Sonlar, vaqtlar va xorijiy ismlarni o'qilishi bo'yicha yozish (standart: hamma dvijoklar uchun)."""
    mode = (config.TTS_NORMALIZE or "on").lower()
    return eng.normalize_numbers if mode == "auto" else mode in ("on", "1", "true", "yes")


def _finalize(pieces: list[Path], dest: Path) -> None:
    """Bo'laklarni birlashtiradi, ovoz balandligini tekislaydi (EBU R128), oxiriga pauza qo'shadi."""
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces))
    af = f"loudnorm=I={config.TTS_LOUDNESS}:TP=-1.5:LRA=11,apad=pad_dur={END_PAD}"
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                        "-af", af, "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k",
                        str(dest)], capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        raise TTSError(f"FFmpeg audioni birlashtira olmadi: {r.stderr[-300:]}")


def _fix_cues(cues, sents, total):
    """Vaqtlar soni gaplar soniga teng, o'suvchi va audio uzunligi ichida bo'lishini kafolatlaydi."""
    if len(cues) != len(sents):
        from .base import proportional
        return proportional(sents, total - END_PAD)
    out, prev = [], 0.0
    for a, b, s in cues:
        a = min(max(a, prev), total)
        b = min(max(b, a + 0.05), total)
        out.append((a, b, s))
        prev = a
    return out


def section(eng: Engine, text: str, dest: Path) -> tuple[float, list]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    sents = sentences(text)
    if not sents:
        raise TTSError("Bo'lim matni bo'sh")
    full = _normalize_numbers(eng)
    spoken = [uz_text.for_speech(s, full=full, apostrophe=getattr(eng, "apostrophe", "'")) for s in sents]
    pieces, cues = eng.synth(spoken, sents, dest.with_suffix(""))
    _finalize(pieces, dest)
    errors, warns, info = audio_qa.check(dest, sum(len(s) for s in spoken))
    if errors:
        raise TTSError("; ".join(errors))
    for w in warns:
        print(f"  ⚠️ {w}")
        warnings.append(w)
    total = duration(dest)
    return total, _fix_cues(cues, sents, total)


def synthesize_sections(texts: list[str], dests: list[Path]) -> list[tuple[float, list]]:
    """Barcha bo'limlarni bitta dvijok bilan yozadi; yiqilsa — keyingi dvijok bilan hammasini qaytadan."""
    global last_label
    warnings.clear()
    failures = []
    for name in chain():
        try:
            eng = engine(name)
        except TTSError as e:
            failures.append(f"{name}: {e}")
            continue
        ok, why = eng.available()
        if not ok:
            failures.append(f"{name}: {why}")
            print(f"  ⚠️ {name} ishlatib bo'lmaydi: {why}")
            continue
        print(f"  🎙 Ovoz dvijoki: {eng.label()}")
        t0 = time.time()
        try:
            out = []
            for i, (t, d) in enumerate(zip(texts, dests)):
                out.append(section(eng, t, d))
                print(f"    {i + 1}/{len(texts)} bo'lim: {out[-1][0]:.0f} s")
            last_label = eng.label()
            if failures:
                warnings.insert(0, "Asosiy ovoz ishlamadi, zaxira ishlatildi: " + " | ".join(failures))
            print(f"  Ovoz tayyor: {sum(d for d, _ in out):.0f} s, {time.time() - t0:.0f} s ichida")
            return out
        except Exception as e:
            msg = _redact(f"{name}: {str(e)[:400]}")
            failures.append(msg)
            print(f"  ❌ {msg}")
    raise TTSError("Hech bir ovoz dvijoki ishlamadi — " + " | ".join(failures))
