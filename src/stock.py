"""Bepul stok videolar: Pexels (https://www.pexels.com/api/) yoki
Pixabay (https://pixabay.com/api/docs/). Qaysi kalit bo'lsa, o'sha ishlatiladi.

Har bir sahna uchun inglizcha qidiruv so'zi bo'yicha landshaft video topadi va
yuklab oladi. Bir video bir rolikda ikki marta ishlatilmaydi.
"""
from pathlib import Path

import requests

from . import config

SEARCH = "https://api.pexels.com/v1/videos/search"
_used: set[int] = set()
credits: dict[int, str] = {}   # video_id -> muallif ismi (tavsifda ko'rsatiladi)
sources: set[str] = set()      # "Pexels" / "Pixabay" — tavsifda ko'rsatiladi


def enabled() -> bool:
    return bool(config.PEXELS_API_KEY() or config.PIXABAY_API_KEY())


def _pick_file(files: list[dict]) -> dict | None:
    mp4 = [f for f in files if f.get("file_type") == "video/mp4"
           and f.get("width") and f.get("height") and f["width"] > f["height"]]
    # 1920 ga eng yaqin, lekin 1280 dan kichik bo'lmagan fayl (hajmi ham katta bo'lmasin)
    good = [f for f in mp4 if f["width"] >= 1280]
    pool = good or mp4
    if not pool:
        return None
    return min(pool, key=lambda f: abs(f["width"] - 1920))


def fetch(query: str, dest: Path, min_seconds: float = 4) -> Path | None:
    """So'rov bo'yicha bitta video yuklaydi. Topilmasa None qaytaradi."""
    got = None
    if config.PEXELS_API_KEY():
        got = _pexels(query, dest, min_seconds)
    if got is None and config.PIXABAY_API_KEY():
        got = _pixabay(query, dest, min_seconds)
    return got


def _download(url: str, dest: Path) -> bool:
    data = requests.get(url, timeout=120)
    if data.status_code != 200 or len(data.content) < 50_000:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data.content)
    return True


def _pixabay(query: str, dest: Path, min_seconds: float) -> Path | None:
    try:
        r = requests.get("https://pixabay.com/api/videos/",
                         params={"key": config.PIXABAY_API_KEY(), "q": query[:100],
                                 "video_type": "film", "per_page": 15, "min_width": 1280,
                                 "safesearch": "true"}, timeout=30)
        if r.status_code != 200:
            print(f"  Pixabay {r.status_code}: {r.text[:120]}")
            return None
        for v in r.json().get("hits", []):
            vid = 10**12 + v["id"]  # Pexels id'lari bilan to'qnashmasin
            if vid in _used or v.get("duration", 0) < min_seconds:
                continue
            vids = v.get("videos", {})
            f = vids.get("medium") or {}
            if not f.get("url") or f.get("width", 0) < f.get("height", 1):
                continue
            if not _download(f["url"], dest):
                continue
            _used.add(vid)
            credits[vid] = v.get("user", "Pixabay")
            sources.add("Pixabay")
            return dest
    except Exception as e:
        print(f"  Pixabay xatosi: {str(e)[:150]}")
    return None


def _pexels(query: str, dest: Path, min_seconds: float) -> Path | None:
    try:
        r = requests.get(SEARCH, headers={"Authorization": config.PEXELS_API_KEY()},
                         params={"query": query, "orientation": "landscape",
                                 "size": "medium", "per_page": 15}, timeout=30)
        if r.status_code != 200:
            print(f"  Pexels {r.status_code}: {r.text[:120]}")
            return None
        for v in r.json().get("videos", []):
            if v["id"] in _used or v.get("duration", 0) < min_seconds:
                continue
            f = _pick_file(v.get("video_files", []))
            if not f:
                continue
            if not _download(f["link"], dest):
                continue
            _used.add(v["id"])
            credits[v["id"]] = (v.get("user") or {}).get("name", "Pexels")
            sources.add("Pexels")
            return dest
    except Exception as e:
        print(f"  Pexels xatosi: {str(e)[:150]}")
    return None
