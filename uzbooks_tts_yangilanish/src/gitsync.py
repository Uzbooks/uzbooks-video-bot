"""Navbat faylini (state/queue.json) GitHub'dagi eng yangi holat bilan sinxronlash.

Listener (bot) va video tayyorlovchi ish bir vaqtda ishlaydi, ikkalasi ham navbatni
o'zgartiradi. Shuning uchun har yozishdan oldin GitHub'dagi eng yangi nusxa olinadi.
GitHub Actions'dan tashqarida (lokal sinovda) hech narsa qilmaydi.
"""
import json
import os
import subprocess
import time

from . import config
from .queue_merge import merge


def enabled() -> bool:
    return os.environ.get("GITHUB_ACTIONS") == "true"


def _git(*args, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "user.name=uzbooks-bot", "-c", "user.email=bot@users.noreply.github.com",
                           *args], cwd=config.ROOT, capture_output=True, text=True, check=check)


def _load() -> dict:
    if config.QUEUE_FILE.exists():
        return json.loads(config.QUEUE_FILE.read_text(encoding="utf-8"))
    return {"offset": 0, "books": []}


def _save(q: dict) -> None:
    config.QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.QUEUE_FILE.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")


def _commit_push(message: str) -> bool:
    _git("add", str(config.QUEUE_FILE.relative_to(config.ROOT)))
    if _git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return True                                   # o'zgarish yo'q
    _git("commit", "-q", "-m", message)
    return _git("push", "-q", "origin", "HEAD:main", check=False).returncode == 0


def latest() -> dict:
    """GitHub'dagi eng yangi navbat (lokal faylni ham yangilaydi)."""
    if enabled():
        _git("fetch", "-q", "origin", "main")
        _git("reset", "-q", "--hard", "origin/main")
    return _load()


def update(fn, message: str) -> dict:
    """Eng yangi navbatni olib, fn(q) bilan o'zgartiradi va GitHub'ga saqlaydi."""
    for attempt in range(6):
        q = latest()
        fn(q)
        _save(q)
        if not enabled() or _commit_push(message):
            return q
        time.sleep(2 + attempt * 2)
    raise RuntimeError("Navbatni GitHub'ga saqlab bo'lmadi")


def push_local(message: str) -> dict:
    """Lokal o'zgarishlarni (status va h.k.) GitHub'dagi navbat bilan birlashtirib saqlaydi."""
    ours = _load()
    if not enabled():
        return ours
    return update(lambda q: q.update(merge(ours, q)), message)
