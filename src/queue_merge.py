"""Navbat faylini xavfsiz birlashtirish.

Video tayyorlanayotgan paytda Cloudflare Worker navbatga yangi kitob qo'shishi mumkin.
Shuning uchun ish oxirida: GitHub'dagi eng yangi navbat + bizning holat yangilanishlarimiz.
  python -m src.queue_merge BIZNIKI.json GITHUBDAGI.json  -> natija GITHUBDAGI.json ga yoziladi
"""
import json
import sys
from pathlib import Path


def merge(ours: dict, theirs: dict) -> dict:
    mine = {b["id"]: b for b in ours.get("books", [])}
    out = []
    for b in theirs.get("books", []):
        m = mine.pop(b["id"], None)
        if m and m.get("status") != "queued":      # biz ishlagan kitob — bizning holat to'g'ri
            b = m
        elif b.get("status") == "removed":
            pass
        out.append(b)
    out += list(mine.values())                      # faqat bizda bo'lganlar (getUpdates orqali kelgan)
    return {"offset": max(ours.get("offset", 0), theirs.get("offset", 0)), "books": out}


if __name__ == "__main__":
    ours = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    tp = Path(sys.argv[2])
    theirs = json.loads(tp.read_text(encoding="utf-8")) if tp.exists() else {"offset": 0, "books": []}
    tp.write_text(json.dumps(merge(ours, theirs), ensure_ascii=False, indent=2), encoding="utf-8")
