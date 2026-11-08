"""Edge TTS — bepul (Microsoft uz-UZ-SardorNeural / uz-UZ-MadinaNeural). API kalit kerak emas."""
import asyncio
import time
from pathlib import Path

from .base import Engine, TTSError, chunks_by_sentences, duration, proportional


class EdgeEngine(Engine):
    name = "edge"

    def __init__(self, voice: str = "uz-UZ-SardorNeural", timeout: float = 180, attempts: int = 4,
                 apostrophe: str = "'"):
        super().__init__(voice)
        self.apostrophe = apostrophe or "'"         # ' yoki ʻ (qaysi biri yaxshi o'qilishini tts_test aniqlaydi)
        self.timeout, self.attempts = timeout, attempts

    def label(self):
        return f"edge:{self.voice}" + (" (ʻ)" if self.apostrophe != "'" else "")

    def available(self):
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False, "edge-tts kutubxonasi o'rnatilmagan"
        return True, ""

    def _chunk(self, text: str, dest: Path) -> list:
        import edge_tts
        events = []

        async def run():
            try:
                comm = edge_tts.Communicate(text, self.voice, boundary="SentenceBoundary")
            except TypeError:                      # eski versiya
                comm = edge_tts.Communicate(text, self.voice)
            with open(dest, "wb") as f:
                async for ch in comm.stream():
                    if ch["type"] == "audio":
                        f.write(ch["data"])
                    elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                        events.append((ch["type"], ch["offset"] / 1e7,
                                       (ch["offset"] + ch["duration"]) / 1e7, ch.get("text", "")))

        last = ""
        for attempt in range(self.attempts):
            try:
                events.clear()
                asyncio.run(asyncio.wait_for(run(), self.timeout))
                if dest.exists() and dest.stat().st_size > 1000:
                    return events
                last = "bo'sh audio qaytdi"
            except asyncio.TimeoutError:
                last = f"{self.timeout:.0f} s ichida javob kelmadi"
            except Exception as e:
                last = str(e)[:150]
            print(f"  Edge TTS xatosi ({attempt + 1}/{self.attempts}): {last}")
            time.sleep(10 * (attempt + 1))
        raise TTSError(f"Edge TTS ovoz yarata olmadi: {last}")

    @staticmethod
    def _cues(sents, events, total, spoken=None):
        """sents — subtitr uchun asl gaplar; spoken — ovozga ketgan matn (so'z sanash uchun)."""
        spoken = spoken or sents
        sb = [e for e in events if e[0] == "SentenceBoundary"]
        if len(sb) == len(sents):
            return [(a, b, s) for (_, a, b, _), s in zip(sb, sents)]
        wb = [e for e in events if e[0] == "WordBoundary"]
        counts = [len(x.split()) for x in spoken]
        if wb and abs(len(wb) - sum(counts)) <= max(3, sum(counts) // 20):
            cues, k = [], 0
            for c, s in zip(counts, sents):
                first = wb[min(k, len(wb) - 1)]
                last = wb[min(k + c - 1, len(wb) - 1)]
                cues.append((first[1], last[2], s))
                k += c
            return cues
        return proportional(sents, total)

    def synth(self, spoken, original, stem):
        pieces, cues, offset = [], [], 0.0
        for k, group in enumerate(chunks_by_sentences(list(range(len(spoken))), spoken)):
            raw = stem.with_name(f"{stem.name}_edge{k}.mp3")
            events = self._chunk(" ".join(spoken[i] for i in group), raw)
            d = duration(raw)
            part = self._cues([original[i] for i in group], events, d, [spoken[i] for i in group])
            cues += [(a + offset, b + offset, s) for a, b, s in part]
            pieces.append(raw)
            offset += d
        return pieces, cues
