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


END_PAD = 0.7   # bo'lim oxiridagi pauza (soniya)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _sentence_spans(text: str, sents: list[str]) -> list[tuple[int, int]]:
    spans, pos = [], 0
    for snt in sents:
        i = text.find(snt, pos)
        if i < 0:
            i = pos
        spans.append((i, min(len(text), i + len(snt))))
        pos = i + len(snt)
    return spans


def _proportional(sents: list[str], total: float) -> list[tuple[float, float, str]]:
    n = sum(len(x) for x in sents) or 1
    t, out = 0.0, []
    for x in sents:
        d = total * len(x) / n
        out.append((t, t + d, x))
        t += d
    return out


def _cues_from_chars(text, sents, starts, ends, total):
    """Harf darajasidagi vaqtlardan har bir gapning boshlanish/tugash vaqtini topadi."""
    if not starts or len(starts) != len(text):
        return _proportional(sents, total)
    cues = []
    for (a, b), snt in zip(_sentence_spans(text, sents), sents):
        a = min(a, len(starts) - 1)
        b = max(a, min(b - 1, len(ends) - 1))
        cues.append((float(starts[a]), float(ends[b]), snt))
    return cues


# ---------------- ElevenLabs (butun bo'lim bitta so'rovda — tabiiy intonatsiya) ----------------
def _eleven_chunk(text: str, dest: Path) -> tuple[list, list]:
    import base64
    global _send_lang
    url = (f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID()}"
           f"/with-timestamps?output_format=mp3_44100_128")
    for attempt in range(5):
        body = {"text": text, "model_id": config.ELEVENLABS_MODEL}
        if _send_lang:
            body["language_code"] = "uz"
        stab = config.env("ELEVENLABS_STABILITY")
        if stab:
            body["voice_settings"] = {"stability": float(stab)}
        r = requests.post(url, headers={"xi-api-key": config.ELEVENLABS_API_KEY(),
                                        "Content-Type": "application/json"}, json=body, timeout=600)
        if r.status_code == 200:
            data = r.json()
            dest.write_bytes(base64.b64decode(data["audio_base64"]))
            al = data.get("alignment") or {}
            return (al.get("character_start_times_seconds") or [],
                    al.get("character_end_times_seconds") or [])
        if r.status_code == 400 and _send_lang and "language_code" in r.text:
            print("  ElevenLabs language_code='uz' ni qabul qilmadi, tilni avtomatik aniqlashga o'tamiz")
            _send_lang = False
            continue
        if r.status_code in (429, 500, 502, 503):
            time.sleep(15 * (attempt + 1))
            continue
        raise RuntimeError(f"ElevenLabs xatosi {r.status_code}: {r.text[:300]}")
    raise RuntimeError("ElevenLabs javob bermadi")


# ---------------- Edge TTS (bepul) ----------------
def _edge_chunk(text: str, dest: Path) -> list[tuple[float, float, str]]:
    import asyncio
    import edge_tts

    events = []

    async def run():
        try:
            comm = edge_tts.Communicate(text, config.EDGE_VOICE, boundary="SentenceBoundary")
        except TypeError:  # eski versiya
            comm = edge_tts.Communicate(text, config.EDGE_VOICE)
        with open(dest, "wb") as f:
            async for ch in comm.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                    events.append((ch["type"], ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7,
                                   ch.get("text", "")))

    for attempt in range(4):
        try:
            events.clear()
            asyncio.run(run())
            if dest.exists() and dest.stat().st_size > 1000:
                return events
        except Exception as e:
            print(f"  Edge TTS xatosi ({attempt+1}/4): {str(e)[:150]}")
        time.sleep(10 * (attempt + 1))
    raise RuntimeError("Edge TTS ovoz yarata olmadi")


def _edge_cues(sents, events, total):
    sb = [e for e in events if e[0] == "SentenceBoundary"]
    if len(sb) == len(sents):
        return [(a, b, snt) for (_, a, b, _), snt in zip(sb, sents)]
    wb = [e for e in events if e[0] == "WordBoundary"]
    counts = [len(x.split()) for x in sents]
    if wb and abs(len(wb) - sum(counts)) <= max(3, sum(counts) // 20):
        cues, k = [], 0
        for c, snt in zip(counts, sents):
            first = wb[min(k, len(wb) - 1)]
            last = wb[min(k + c - 1, len(wb) - 1)]
            cues.append((first[1], last[2], snt))
            k += c
        return cues
    return _proportional(sents, total)


def _chunks_by_sentences(sents: list[str], limit: int = 2500) -> list[list[str]]:
    out, cur, n = [], [], 0
    for snt in sents:
        if cur and n + len(snt) > limit:
            out.append(cur)
            cur, n = [], 0
        cur.append(snt)
        n += len(snt) + 1
    if cur:
        out.append(cur)
    return out


def synthesize_with_cues(text: str, dest: Path) -> tuple[float, list[tuple[float, float, str]]]:
    """Bo'limni BIR butun matn sifatida ovozga aylantiradi (gapma-gap emas — shuning uchun
    intonatsiya tabiiy chiqadi) va har bir gapning vaqtini qaytaradi (subtitr va sahnalar uchun)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    sents = sentences(text)
    pieces, cues, offset = [], [], 0.0
    for k, group in enumerate(_chunks_by_sentences(sents)):
        orig = " ".join(group)
        spoken = _normalize(orig)              # apostroflarni almashtirish uzunlikni o'zgartirmaydi
        raw = dest.with_name(f"{dest.stem}_c{k}.mp3")
        if provider() == "elevenlabs":
            starts, ends = _eleven_chunk(spoken, raw)
            d = duration(raw)
            part = _cues_from_chars(spoken, [_normalize(x) for x in group], starts, ends, d)
        else:
            events = _edge_chunk(spoken, raw)
            d = duration(raw)
            part = _edge_cues(group, events, d)
        cues += [(a + offset, b + offset, snt) for (a, b, _), snt in zip(part, group)]
        pieces.append(raw)
        offset += d
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in pieces))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-af", f"apad=pad_dur={END_PAD}", "-ar", "44100", "-ac", "2",
                    "-c:a", "libmp3lame", "-b:a", "192k", str(dest)], check=True)
    return duration(dest), cues
