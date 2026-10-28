"""Telegram botni doimiy tinglovchi (GitHub Actions ichida ~6 soat ishlaydi, keyin o'zini qayta ishga tushiradi).

- Xabarlarga 1-3 soniyada javob beradi (/navbat, /start, /ochir, /boshla).
- Kitob yuborilishi bilan uni navbatga qo'shadi va video tayyorlashni ishga tushiradi.
"""
import os
import time

import requests

from . import config, gitsync, telegram_io

BOOK_EXT = telegram_io.BOOK_EXT


def dispatch(task: str) -> bool:
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not repo or not token:
        print(f"[dispatch {task}] GitHub muhiti yo'q — o'tkazib yuborildi")
        return False
    r = requests.post(f"https://api.github.com/repos/{repo}/actions/workflows/uzbooks.yml/dispatches",
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                      json={"ref": "main", "inputs": {"task": task}}, timeout=30)
    if r.status_code != 204:
        print(f"[dispatch {task}] xato {r.status_code}: {r.text[:200]}")
    return r.status_code == 204


def handle(msg: dict) -> None:
    if str(msg.get("chat", {}).get("id", "")) != str(config.TELEGRAM_ADMIN_ID()):
        return
    text = (msg.get("text") or "").strip()
    doc = msg.get("document")

    if doc:
        name = doc.get("file_name", "kitob")
        if not name.lower().endswith(BOOK_EXT):
            telegram_io.send(f"⚠️ {name}: bu format qo'llab-quvvatlanmaydi. PDF, EPUB, TXT, DOCX yoki FB2 yuboring.")
            return
        if doc.get("file_size", 0) > 20 * 1024 * 1024:
            telegram_io.send(f"⚠️ {name}: fayl 20 MB dan katta, Telegram bot uni yuklab ololmaydi.")
            return

        def add(q):
            if not any(b.get("file_id") == doc["file_id"] for b in q["books"]):
                q["books"].append({"id": f"b{int(time.time())}_{len(q['books'])}", "file_id": doc["file_id"],
                                   "file_name": name, "note": (msg.get("caption") or "").strip(),
                                   "status": "queued", "added": time.strftime("%Y-%m-%d %H:%M")})
        q = gitsync.update(add, f"navbatga qo'shildi: {name}")
        pending = len(telegram_io.pending_books(q))
        busy = any(b["status"] == "processing" for b in q["books"])
        dispatch("produce")
        telegram_io.send(f"✅ «{name}» qabul qilindi.\n" + (
            f"Navbatda {pending} ta kitob — oldingilari tugagach, bu ham avtomatik boshlanadi."
            if busy or pending > 1 else
            "⚙️ Video tayyorlash boshlandi (taxminan 20–40 daqiqa). Tayyor bo'lgach video shu yerga keladi."))
        return

    if text in ("/start", "/help"):
        telegram_io.send("Assalomu alaykum! Kitob yoki ssenariy faylini (PDF/EPUB/TXT/DOCX) yuboring — "
                         "video avtomatik tayyorlanadi.\nTayyor ssenariy so'zma-so'z o'qilishi uchun izohga "
                         "«tayyor ssenariy» deb yozing.\n\n/navbat — navbatni ko'rish\n"
                         "/ochir 2 — 2-kitobni navbatdan olib tashlash\n/boshla — tayyorlashni qo'lda boshlash")
    elif text == "/navbat":
        q = gitsync.latest()
        running = [b for b in q["books"] if b["status"] == "processing"]
        pending = telegram_io.pending_books(q)
        if not running and not pending:
            telegram_io.send("📭 Navbat bo'sh.")
            return
        out = ""
        if running:
            out += "⚙️ Hozir tayyorlanmoqda:\n" + "\n".join(f"• {b['file_name']}" for b in running) + "\n\n"
        if pending:
            out += "📚 Navbatda:\n" + "\n".join(f"{i+1}. {b['file_name']}" for i, b in enumerate(pending))
        telegram_io.send(out.strip())
    elif text.startswith("/ochir"):
        try:
            n = int(text.split()[1])
        except Exception:
            telegram_io.send("Foydalanish: /ochir 2  (raqamni /navbat dan oling)")
            return
        removed = {}

        def rm(q):
            pb = telegram_io.pending_books(q)
            if 1 <= n <= len(pb):
                pb[n - 1]["status"] = "removed"
                removed["name"] = pb[n - 1]["file_name"]
        gitsync.update(rm, "navbatdan olib tashlandi")
        telegram_io.send(f"🗑 «{removed['name']}» navbatdan olib tashlandi." if removed
                         else "Bunday raqamli kitob yo'q. /navbat ni tekshiring.")
    elif text == "/boshla":
        telegram_io.send("▶️ Tayyorlash ishga tushirildi." if dispatch("produce")
                         else "⚠️ Ishga tushirib bo'lmadi.")


MY_RUN = os.environ.get("GITHUB_RUN_ID", "local")


def _run_alive(run_id) -> bool:
    """Boshqa bot nusxasi (GitHub run) hali ishlayaptimi?"""
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    if not run_id or str(run_id) == MY_RUN or not repo or not token:
        return False
    try:
        r = requests.get(f"https://api.github.com/repos/{repo}/actions/runs/{run_id}",
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
                         timeout=30)
        return r.ok and r.json().get("status") in ("in_progress", "queued", "waiting", "pending", "requested")
    except Exception:
        return False


def _other_listener() -> bool:
    return _run_alive(gitsync.latest().get("listener_run_id"))


def run(minutes: float) -> None:
    deadline = time.time() + minutes * 60
    if _other_listener():
        print("Boshqa bot nusxasi allaqachon ishlayapti — bu nusxa darhol tugaydi.")
        return
    gitsync.update(lambda q: q.update(listener_run_id=MY_RUN), "bot: tinglovchi boshlandi")
    try:  # Cloudflare sinovidan qolgan webhook bo'lsa, o'chiramiz (aks holda getUpdates ishlamaydi)
        telegram_io._call("deleteWebhook", drop_pending_updates=False)
    except Exception as e:
        print(f"deleteWebhook: {e}")
    offset = gitsync.latest().get("offset", 0)
    print(f"Bot tinglanmoqda ({minutes:.0f} daqiqa)...")
    conflicts = 0
    while time.time() < deadline:
        try:
            ups = telegram_io._call("getUpdates", offset=offset, timeout=50, allowed_updates=["message"])
            conflicts = 0
        except Exception as e:
            print(f"getUpdates xatosi: {str(e)[:200]}")
            if "409" in str(e) or "onflict" in str(e):
                conflicts += 1
                if conflicts > 3 and gitsync.latest().get("listener_run_id") != MY_RUN:
                    print("Boshqa bot nusxasi ishlayapti — bu nusxa to'xtaydi.")
                    return
            time.sleep(5)
            continue
        for u in ups:
            offset = u["update_id"] + 1
            try:
                handle(u.get("message") or {})
            except Exception as e:
                print(f"Xabarni ishlashda xato: {e}")
                try:
                    telegram_io.send(f"⚠️ Bot xatosi: {str(e)[:300]}")
                except Exception:
                    pass
        if ups:
            gitsync.update(lambda q: q.update(offset=max(q.get("offset", 0), offset)), "bot: offset")
    # vaqt tugadi — o'zimizni qayta ishga tushiramiz (navbatdagi ish shu tugashi bilan boshlanadi)
    def finish(q):
        q.update(offset=max(q.get("offset", 0), offset))
        if q.get("listener_run_id") == MY_RUN:
            q["listener_run_id"] = None
    gitsync.update(finish, "bot: offset")
    dispatch("listen")


if __name__ == "__main__":
    import sys
    run(float(sys.argv[1]) if len(sys.argv) > 1 else 340)
