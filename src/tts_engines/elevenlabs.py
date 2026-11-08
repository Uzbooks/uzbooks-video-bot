"""ElevenLabs (pullik, ixtiyoriy). Butun bo'lim bitta so'rovda + harf darajasidagi vaqtlar."""
import base64
import time

import requests

from .base import Engine, TTSError, chunks_by_sentences, duration, proportional

_send_lang = True   # API language_code='uz' ni rad etsa, o'chiramiz


def _spans(text, sents):
    spans, pos = [], 0
    for s in sents:
        i = text.find(s, pos)
        if i < 0:
            i = pos
        spans.append((i, min(len(text), i + len(s))))
        pos = i + len(s)
    return spans


def cues_from_chars(text, spoken, original, starts, ends, total):
    if not starts or len(starts) != len(text):
        return proportional(original, total)
    cues = []
    for (a, b), s in zip(_spans(text, spoken), original):
        a = min(a, len(starts) - 1)
        b = max(a, min(b - 1, len(ends) - 1))
        cues.append((float(starts[a]), float(ends[b]), s))
    return cues


class ElevenLabsEngine(Engine):
    name = "elevenlabs"

    def __init__(self, api_key: str, voice: str, model: str = "eleven_v3", stability: str = "",
                 timeout: float = 600):
        super().__init__(voice)
        self._key, self.model, self.stability, self.timeout = api_key, model, stability, timeout

    def label(self):
        return f"elevenlabs:{self.model}"        # voice ID ni logga chiqarmaymiz

    def available(self):
        if not self._key or not self.voice:
            return False, "ELEVENLABS_API_KEY yoki ELEVENLABS_VOICE_ID berilmagan"
        return True, ""

    def _chunk(self, text, dest):
        global _send_lang
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice}"
               f"/with-timestamps?output_format=mp3_44100_128")
        last = ""
        for attempt in range(5):
            body = {"text": text, "model_id": self.model}
            if _send_lang:
                body["language_code"] = "uz"
            if self.stability:
                body["voice_settings"] = {"stability": float(self.stability)}
            try:
                r = requests.post(url, headers={"xi-api-key": self._key, "Content-Type": "application/json"},
                                  json=body, timeout=self.timeout)
            except requests.RequestException as e:
                last = f"tarmoq xatosi: {type(e).__name__}"
                time.sleep(15 * (attempt + 1))
                continue
            if r.status_code == 200:
                data = r.json()
                dest.write_bytes(base64.b64decode(data["audio_base64"]))
                al = data.get("alignment") or {}
                return (al.get("character_start_times_seconds") or [],
                        al.get("character_end_times_seconds") or [])
            if r.status_code == 400 and _send_lang and "language_code" in r.text:
                print("  ElevenLabs language_code='uz' ni qabul qilmadi, avtomatik aniqlashga o'tamiz")
                _send_lang = False
                continue
            last = f"{r.status_code}: {r.text[:200]}"
            if r.status_code in (429, 500, 502, 503):
                time.sleep(15 * (attempt + 1))
                continue
            break
        raise TTSError(f"ElevenLabs xatosi {last}")

    def synth(self, spoken, original, stem):
        pieces, cues, offset = [], [], 0.0
        for k, group in enumerate(chunks_by_sentences(list(range(len(spoken))), spoken)):
            text = " ".join(spoken[i] for i in group)
            raw = stem.with_name(f"{stem.name}_el{k}.mp3")
            starts, ends = self._chunk(text, raw)
            d = duration(raw)
            part = cues_from_chars(text, [spoken[i] for i in group], [original[i] for i in group],
                                   starts, ends, d)
            cues += [(a + offset, b + offset, s) for a, b, s in part]
            pieces.append(raw)
            offset += d
        return pieces, cues
