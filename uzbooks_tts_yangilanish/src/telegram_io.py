"""Telegram bot: kitoblarni qabul qilish (navbat) va adminga xabar yuborish.

Diqqat: Telegram yangilanishlarni faqat 24 soat saqlaydi, shuning uchun
`collect` har soatda ishga tushadi va kitoblarni state/queue.json ga yozadi.
"""
import json
import time
from pathlib import Path

import requests

from . import config

API = "https://api.telegram.org/bot{token}/{method}"
BOOK_EXT = (".pdf", ".epub", ".txt", ".docx", ".fb2")


def _call(method: str, **kwargs):
    url = API.format(token=config.TELEGRAM_BOT_TOKEN(), method=method)
    files = kwargs.pop("files", None)
    r = requests.post(url, data=kwargs if files else None,
                      json=None if files else kwargs, files=files, timeout=120)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} xatosi: {data}")
    return data["result"]


# ---------------- navbat (queue) ----------------
def load_queue() -> dict:
    if config.QUEUE_FILE.exists():
        return json.loads(config.QUEUE_FILE.read_text(encoding="utf-8"))
    return {"offset": 0, "books": []}


def save_queue(q: dict) -> None:
    config.QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.QUEUE_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2),
                                 encoding="utf-8")


def pending_books(q: dict) -> list[dict]:
    return [b for b in q["books"] if b["status"] in ("queued", "failed_retry")]


def send(text: str) -> None:
    for i in range(0, len(text), 4000):  # Telegram limiti 4096 belgi
        _call("sendMessage", chat_id=config.TELEGRAM_ADMIN_ID(),
              text=text[i:i + 4000], disable_web_page_preview=True)


def send_photo(path: Path, caption: str) -> None:
    with open(path, "rb") as f:
        _call("sendPhoto", chat_id=config.TELEGRAM_ADMIN_ID(),
              caption=caption[:1000], files={"photo": f})


def send_document(path: Path, caption: str = "") -> None:
    with open(path, "rb") as f:
        _call("sendDocument", chat_id=config.TELEGRAM_ADMIN_ID(),
              caption=caption[:1000], files={"document": f})


def collect() -> int:
    """Botga kelgan yangi kitob fayllarini navbatga qo'shadi. Qo'shilganlar sonini qaytaradi."""
    q = load_queue()
    admin = str(config.TELEGRAM_ADMIN_ID())
    try:
        updates = _call("getUpdates", offset=q["offset"], timeout=0, allowed_updates=["message"])
    except RuntimeError as e:
        if "409" in str(e) or "webhook" in str(e).lower():
            print("Bot webhook (Cloudflare Worker) orqali ishlayapti — collect kerak emas.")
            return 0
        raise
    added = 0
    for u in updates:
        q["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != admin:
            continue  # begonalardan kelgan xabarlarni e'tiborsiz qoldiramiz
        text = (msg.get("text") or "").strip()
        doc = msg.get("document")
        if doc:
            name = doc.get("file_name", "kitob")
            if not name.lower().endswith(BOOK_EXT):
                send(f"⚠️ {name}: bu format qo'llab-quvvatlanmaydi. "
                     f"PDF, EPUB, TXT, DOCX yoki FB2 yuboring.")
                continue
            if doc.get("file_size", 0) > 20 * 1024 * 1024:
                send(f"⚠️ {name}: fayl 20 MB dan katta. Telegram bot bunday faylni "
                     f"yuklab ololmaydi. Kichikroq versiyasini yuboring.")
                continue
            q["books"].append({
                "id": f"b{int(time.time())}_{len(q['books'])}",
                "file_id": doc["file_id"], "file_name": name,
                "note": (msg.get("caption") or "").strip(),
                "status": "queued", "added": time.strftime("%Y-%m-%d %H:%M"),
            })
            added += 1
            send(f"✅ «{name}» navbatga qo'shildi. Navbatda: "
                 f"{len(pending_books(q))} ta kitob.")
        elif text in ("/start", "/help"):
            send("Assalomu alaykum! Kitob faylini (PDF/EPUB/TXT/DOCX) shu yerga "
                 "yuboring — u navbatga tushadi.\n/navbat — navbatni ko'rish\n"
                 "/ochir <raqam> — navbatdan olib tashlash")
        elif text == "/navbat":
            pb = pending_books(q)
            send("Navbat bo'sh." if not pb else "📚 Navbat:\n" + "\n".join(
                f"{i+1}. {b['file_name']}" for i, b in enumerate(pb)))
        elif text.startswith("/ochir"):
            pb = pending_books(q)
            try:
                b = pb[int(text.split()[1]) - 1]
                b["status"] = "removed"
                send(f"🗑 «{b['file_name']}» navbatdan olib tashlandi.")
            except Exception:
                send("Foydalanish: /ochir 2")
    save_queue(q)
    return added


def download(file_id: str, dest: Path) -> Path:
    info = _call("getFile", file_id=file_id)
    url = f"https://api.telegram.org/file/bot{config.TELEGRAM_BOT_TOKEN()}/{info['file_path']}"
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


# ---------------- tayyor videoni Telegramga yuborish ----------------
TG_LIMIT = 49 * 1024 * 1024   # Bot API orqali yuborish chegarasi ~50 MB


def _probe(path: Path) -> tuple[float, int, int]:
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "default=nw=1", str(path)],
                         capture_output=True, text=True).stdout
    vals = dict(l.split("=", 1) for l in out.split() if "=" in l)
    return float(vals.get("duration", 0)), int(vals.get("width", 0)), int(vals.get("height", 0))


def telegram_versions(video: Path) -> list[Path]:
    """Telegram'ga sig'adigan nusxa(lar): kerak bo'lsa 720p ga siqadi, baribir katta bo'lsa bo'laklarga bo'ladi."""
    import math
    import subprocess
    if video.stat().st_size <= TG_LIMIT:
        return [video]
    dur, _, _ = _probe(video)
    total_kbps = int(TG_LIMIT * 0.92 * 8 / 1024 / max(dur, 1))
    v_kbps = max(350, total_kbps - 96)
    small = video.with_name("video_telegram.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(video), "-vf", "scale=-2:720",
                    "-c:v", "libx264", "-preset", "veryfast", "-b:v", f"{v_kbps}k",
                    "-maxrate", f"{int(v_kbps * 1.3)}k", "-bufsize", f"{v_kbps * 2}k",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", str(small)], check=True)
    if small.stat().st_size <= TG_LIMIT:
        return [small]
    n = math.ceil(small.stat().st_size / (TG_LIMIT * 0.9))
    part_len = dur / n
    parts = []
    for i in range(n):
        p = video.with_name(f"video_telegram_{i+1}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{i * part_len:.2f}", "-i", str(small),
                        "-t", f"{part_len:.2f}", "-c", "copy", "-movflags", "+faststart", str(p)], check=True)
        parts.append(p)
    return parts


def send_video(path: Path, caption: str = "") -> None:
    dur, w, h = _probe(path)
    with open(path, "rb") as f:
        url = API.format(token=config.TELEGRAM_BOT_TOKEN(), method="sendVideo")
        for attempt in range(3):
            f.seek(0)
            r = requests.post(url, data={"chat_id": config.TELEGRAM_ADMIN_ID(), "caption": caption[:1000],
                                         "supports_streaming": "true", "duration": int(dur),
                                         "width": w, "height": h},
                              files={"video": (path.name, f, "video/mp4")}, timeout=900)
            if r.ok and r.json().get("ok"):
                return
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Videoni Telegramga yuborib bo'lmadi: {r.text[:200]}")
