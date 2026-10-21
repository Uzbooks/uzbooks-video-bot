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
    updates = _call("getUpdates", offset=q["offset"], timeout=0,
                    allowed_updates=["message"])
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
