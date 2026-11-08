"""Aisha TTS (aisha.group / voicelab.uz) — o'zbek tiliga maxsus o'rgatilgan ovoz.

Narx: ~1 so'm / belgi (10 daqiqalik video ≈ 9 000 belgi ≈ 9 000 so'm). Kalit: AISHA_API_KEY (Secret).
Ovoz: o'rnatilgan "Gulnoza" (ayol) yoki voicelab.uz'da yaratgan o'z ovozingiz (AISHA_VOICE_ID).
Har bir gap alohida so'rov bilan o'qiladi (limit 1000 belgi) — subtitr vaqtlari aniq chiqadi.
"""
import re
import subprocess
import time
from pathlib import Path

import requests

from .base import Engine, TTSError, duration

BASE = "https://back.aisha.group"
LIMIT = 950


def split_long(sentence: str, limit: int = LIMIT) -> list[str]:
    if len(sentence) <= limit:
        return [sentence]
    parts, cur = [], ""
    for piece in re.split(r"(?<=[,;:—–])\s+|\s+", sentence):
        if cur and len(cur) + len(piece) + 1 > limit:
            parts.append(cur)
            cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        parts.append(cur)
    return parts


class AishaEngine(Engine):
    name = "aisha"
    normalize_numbers = True

    def __init__(self, api_key: str, model: str = "Gulnoza", mood: str = "Neutral", speed: str = "1.0",
                 voice_id: str = "", timeout: float = 120, pause: float = 0.3):
        super().__init__(f"voice_id:{voice_id}" if voice_id else f"{model} ({mood})")
        self._key = (api_key or "").strip().strip('"').strip("'")   # nusxalashda qo'shilgan bo'sh joy/qo'shtirnoq
        self.model, self.mood, self.speed = model, mood, speed
        self.voice_id, self.timeout, self.pause = voice_id, timeout, pause
        self.chars = 0

    def available(self):
        if not self._key:
            return False, "AISHA_API_KEY berilmagan (voicelab.uz/app → API kalit, GitHub Secrets'ga qo'shing)"
        return True, ""

    def _request(self, text: str, dest: Path) -> None:
        data = {"transcript": text, "language": "uz", "speed": self.speed or "1.0"}
        if self.voice_id:
            data["voice_id"] = self.voice_id
        else:
            data.update(model=self.model, mood=self.mood)
        last = ""
        for attempt in range(5):
            try:
                r = requests.post(f"{BASE}/api/v1/tts/post/", data=data, timeout=self.timeout,
                                  headers={"X-Api-Key": self._key, "Accept-Language": "uz"})
            except requests.RequestException as e:
                last = f"tarmoq xatosi: {type(e).__name__}"
                time.sleep(5 * (attempt + 1))
                continue
            if r.status_code in (200, 201):
                path = (r.json() or {}).get("audio_path") or ""
                if not path:
                    raise TTSError("Aisha javobida audio_path yo'q")
                url = path if path.startswith("http") else BASE + path
                a = requests.get(url, timeout=self.timeout)
                if a.status_code == 200 and len(a.content) > 500:
                    dest.write_bytes(a.content)
                    self.chars += len(text)
                    return
                last = f"audio yuklab olinmadi ({a.status_code})"
            elif r.status_code == 402:
                raise TTSError("Aisha: balans yetarli emas — voicelab.uz'da hisobni to'ldiring")
            elif r.status_code in (401, 403):
                raise TTSError(f"Aisha: API kalit qabul qilinmadi ({r.status_code}). Server javobi: "
                               f"{r.text[:200]} | Kalit uzunligi: {len(self._key)} belgi")
            elif r.status_code == 400:
                raise TTSError(f"Aisha: noto'g'ri so'rov — {r.text[:200]}")
            else:
                last = f"{r.status_code}: {r.text[:150]}"
            time.sleep(5 * (attempt + 1))
        raise TTSError(f"Aisha javob bermadi: {last}")

    def synth(self, spoken, original, stem):
        pieces, cues, t = [], [], 0.0
        silence = None
        for i, (sp, orig) in enumerate(zip(spoken, original)):
            start = t
            for k, part in enumerate(split_long(sp)):
                p = stem.with_name(f"{stem.name}_aisha{i:03d}_{k}.wav")
                self._request(part, p)
                p = _to_wav(p)
                if silence is None:
                    silence = _silence(p, stem.with_name(f"{stem.name}_aisha_gap.wav"), self.pause)
                pieces.append(p)
                t += duration(p)
            cues.append((start, t, orig))
            pieces.append(silence)
            t += self.pause
        print(f"  Aisha: {self.chars} belgi ishlatildi (~{self.chars} so'm)")
        return pieces, cues


def _to_wav(p: Path) -> Path:
    """Har xil formatda kelsa ham bir xil PCM WAV (24 kHz mono) ga keltiramiz — birlashtirish uchun."""
    out = p.with_name(p.stem + "_n.wav")
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(p), "-ar", "24000", "-ac", "1",
                        "-c:a", "pcm_s16le", str(out)], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise TTSError(f"Aisha audiosi o'qilmadi: {r.stderr[-200:]}")
    return out


def _silence(like: Path, dest: Path, seconds: float) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anullsrc=r=24000:cl=mono", "-t", f"{seconds}", "-c:a", "pcm_s16le", str(dest)],
                   check=True, timeout=60)
    return dest
