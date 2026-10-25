"""O'zbekcha ovoz.

- ElevenLabs (Eleven v3, sifatli; bepul tarifda oyiga ~1 video, tijoriy foydalanishga ruxsat yo'q)
- Edge TTS (bepul, Microsoft'ning uz-UZ ovozlari; API kalit kerak emas)
"""
import re
import subprocess
import time
from pathlib import Path

import requests

from . import config

URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128"
MAX_CHARS = 2800  # v3 da bitta so'rov limiti ~3000 belgi


def _split(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out, cur = [], ""
    for s in sentences:
        if len(cur) + len(s) + 1 > MAX_CHARS and cur:
            out.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        out.append(cur)
    return out


def _normalize(text: str) -> str:
    # TTS uchun turli apostroflarni bir xil qilamiz
    return text.replace("ʻ", "'").replace("ʼ", "'").replace("‘", "'").replace("’", "'")


_send_lang = True  # API language_code ni rad etsa, o'chirib qo'yamiz (model tilni o'zi aniqlaydi)


def _tts(text: str, dest: Path) -> None:
    global _send_lang
    for attempt in range(5):
        body = {"text": text, "model_id": config.ELEVENLABS_MODEL}
        if _send_lang:
            body["language_code"] = "uz"
        r = requests.post(URL.format(voice=config.ELEVENLABS_VOICE_ID()),
                          headers={"xi-api-key": config.ELEVENLABS_API_KEY(),
                                   "Content-Type": "application/json"},
                          json=body, timeout=300)
        if r.status_code == 200:
            dest.write_bytes(r.content)
            return
        if r.status_code == 400 and _send_lang and "language_code" in r.text:
            print("  ElevenLabs language_code='uz' ni qabul qilmadi, tilni avtomatik aniqlashga o'tamiz")
            _send_lang = False
            continue
        if r.status_code in (429, 500, 502, 503):
            time.sleep(15 * (attempt + 1))
            continue
        raise RuntimeError(f"ElevenLabs xatosi {r.status_code}: {r.text[:300]}")
    raise RuntimeError("ElevenLabs javob bermadi")


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(out.stdout.strip())


def provider() -> str:
    p = config.TTS_PROVIDER
    if p == "auto":
        return "elevenlabs" if config.ELEVENLABS_API_KEY() and config.ELEVENLABS_VOICE_ID() else "edge"
    return p


def _edge(text: str, dest: Path) -> None:
    import asyncio
    import edge_tts

    async def run():
        await edge_tts.Communicate(text, config.EDGE_VOICE).save(str(dest))

    for attempt in range(4):
        try:
            asyncio.run(run())
            if dest.exists() and dest.stat().st_size > 1000:
                return
        except Exception as e:
            print(f"  Edge TTS xatosi ({attempt+1}/4): {str(e)[:150]}")
        time.sleep(10 * (attempt + 1))
    raise RuntimeError("Edge TTS ovoz yarata olmadi")


def synthesize_section(text: str, dest: Path) -> float:
    """Bo'lim matnini ovozga aylantiradi, oxirida 0.6 s pauza qo'shadi. Davomiylikni qaytaradi."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    pieces = []
    for i, chunk in enumerate(_split(_normalize(text))):
        p = dest.with_name(f"{dest.stem}_p{i}.mp3")
        (_tts if provider() == "elevenlabs" else _edge)(chunk, p)
        pieces.append(p)
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-af", "apad=pad_dur=0.6", "-ar", "44100", "-ac", "2",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(dest)], check=True)
    return duration(dest)


GAP = 0.18      # gaplar orasidagi pauza (soniya)
END_PAD = 0.6   # bo'lim oxiridagi pauza


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def synthesize_with_cues(text: str, dest: Path) -> tuple[float, list[tuple[float, float, str]]]:
    """Har bir gapni alohida ovozga aylantiradi, shunda subtitr vaqtlari aniq bo'ladi.
    (umumiy davomiylik, [(boshlanish, tugash, gap matni), ...]) qaytaradi."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    engine = _tts if provider() == "elevenlabs" else _edge
    silence = dest.with_name(f"{dest.stem}_gap.mp3")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"anullsrc=r=44100:cl=stereo", "-t", str(GAP), "-c:a", "libmp3lame",
                    "-b:a", "192k", str(silence)], check=True)
    pieces, cues, t = [], [], 0.0
    for i, sent in enumerate(sentences(text)):
        raw = dest.with_name(f"{dest.stem}_s{i:03d}_raw.mp3")
        engine(_normalize(sent), raw)
        p = dest.with_name(f"{dest.stem}_s{i:03d}.mp3")  # bir xil formatga keltiramiz
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-ar", "44100",
                        "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", str(p)], check=True)
        d = duration(p)
        cues.append((t, t + d, sent))
        pieces += [p, silence]
        t += d + GAP
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-af", f"apad=pad_dur={END_PAD}", "-ar", "44100", "-ac", "2",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(dest)], check=True)
    return duration(dest), cues
