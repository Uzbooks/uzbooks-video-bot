"""Barcha ovoz dvijoklari uchun umumiy interfeys.

Har bir dvijok bitta bo'limning gaplarini oladi va:
  - ovoz bo'laklari (fayllar ro'yxati, bir xil formatda, ketma-ket qo'shiladi),
  - har bir gapning vaqti [(boshlanish, tugash, asl_gap), ...] (bo'lim boshidan, soniyada)
qaytaradi. Birlashtirish, ovoz balandligini tekislash va tekshirish — menejer ishi.
"""
import subprocess
from pathlib import Path


class TTSError(RuntimeError):
    """Dvijok ovoz yarata olmadi (menejer zaxira dvijokka o'tadi)."""


class Engine:
    name = "base"
    normalize_numbers = False      # True bo'lsa sonlar so'z bilan yoziladi (uz_text)

    def __init__(self, voice: str = ""):
        self.voice = voice

    def label(self) -> str:
        return f"{self.name}:{self.voice}" if self.voice else self.name

    def available(self) -> tuple[bool, str]:
        return True, ""

    def synth(self, spoken: list[str], original: list[str], stem: Path) -> tuple[list[Path], list]:
        raise NotImplementedError


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        raise TTSError(f"Audio fayl o'qilmadi: {path.name}") from None


def proportional(sents: list[str], total: float, start: float = 0.0) -> list[tuple[float, float, str]]:
    n = sum(len(x) for x in sents) or 1
    t, out = start, []
    for x in sents:
        d = total * len(x) / n
        out.append((t, t + d, x))
        t += d
    return out


def chunks_by_sentences(idx: list[int], sents: list[str], limit: int = 2500) -> list[list[int]]:
    """Gaplarni ~limit belgilik guruhlarga ajratadi (gap o'rtasidan bo'linmaydi)."""
    out, cur, n = [], [], 0
    for i in idx:
        if cur and n + len(sents[i]) > limit:
            out.append(cur)
            cur, n = [], 0
        cur.append(i)
        n += len(sents[i]) + 1
    if cur:
        out.append(cur)
    return out
