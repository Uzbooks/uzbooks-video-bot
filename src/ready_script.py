"""Tayyor ssenariy rejimi: PDF/TXT dagi matn SO'ZMA-SO'Z o'qiladi.

Gemini matnni qayta yozmaydi. U faqat gaplar ro'yxatini bo'limlarga ajratadi
(qaysi gapdan yangi bo'lim boshlanishini raqam bilan aytadi) va sarlavha,
tavsif, teglarni tayyorlaydi. Ovozga ketadigan matn — sizning matningiz.
"""
import re

from . import llm, tts

# Ovozga o'qilmaydigan xizmat qatorlari (bizning ssenariy formatimiz va shunga o'xshashlar)
META_PREFIXES = ("ekrandagi sarlavha", "rasm uchun prompt", "video sarlavhasi", "muqova matni",
                 "davomiyligi", "uzbooks ssenariysi", "uzbooks —", "uzbooks -", "sahna:", "kadr:",
                 "izoh:", "musiqa:")
STOP_MARKERS = ("muqova uchun prompt", "youtube tavsifi", "teglar", "#teglar")
HEADING_RE = re.compile(
    r"^\s*(\d{1,2}:\d{2}\s*[—–-]\s*)?((kirish|yakun|xulosa)(\s*[—–-].*)?|blitz\s*\d+(\s*[—–-].*)?"
    r"|\d+\s*[-.)]?\s*bo['ʻ‘’]?lim.*)\s*$", re.I)
EN_WORDS = {"the", "a", "an", "and", "of", "with", "in", "on", "to", "his", "her", "their",
            "soft", "warm", "toward", "background", "light", "glowing", "style", "while", "into"}


def _is_english(line: str) -> bool:
    words = re.findall(r"[a-zA-Z]+", line.lower())
    return bool(words) and sum(w in EN_WORDS for w in words) >= 2 and "ʻ" not in line
SPOKEN_BLITZ_RE = re.compile(
    r"\bBlitz\s+(bir|ikki|uch|to['ʻ‘’]rt|besh|olti|yetti|sakkiz|to['ʻ‘’]qqiz|o['ʻ‘’]n|\d+)\s*[.:,!]?\s*", re.I)

SEGMENT_SCHEMA = """{
  "book_title": "kitob nomi",
  "author": "muallif (matndan; bilmasang bo'sh qoldir)",
  "video_title": "«Kitob nomi» 10 daqiqada | Muallif | UzBooks (70 belgigacha)",
  "thumbnail_text": "muqova uchun 2-4 so'z, katta harflarda",
  "thumbnail_prompt": "muqova rasmi uchun inglizcha tavsif, matnsiz",
  "description": "YouTube tavsifi o'zbekcha, 3-5 gap",
  "tags": ["8-15 ta teg"],
  "sections": [{"start": 0, "heading": "bo'lim uchun qisqa sarlavha (45 belgigacha)"}]
}"""


def looks_like_script(file_name: str, note: str) -> bool:
    s = f"{file_name} {note}".lower()
    return any(k in s for k in ("ssenariy", "senariy", "scenario", "script", "tayyor matn",
                                "o'zgartirmasdan", "oʻzgartirmasdan", "so'zma-so'z"))


def clean_text(raw: str) -> str:
    keep, in_meta, prev = [], False, ""
    for line in raw.splitlines():
        l = line.strip()
        low = l.lower().lstrip("*# ").strip()
        if not l:
            keep.append("")
            in_meta = False
            continue
        if any(low.startswith(m) for m in STOP_MARKERS):
            break
        if any(low.startswith(p) for p in META_PREFIXES):
            in_meta = True                         # keyingi qatorlar ham shu xizmat yozuvining davomi bo'lishi mumkin
            continue
        if in_meta and (_is_english(l) or (len(l) < 60 and not l.endswith((".", "!", "?", "…")))):
            continue
        in_meta = False
        if re.fullmatch(r"\d{1,3}", l):          # sahifa raqami
            continue
        if HEADING_RE.match(low) and len(l) < 80 and not l.endswith((".", "!", "?")):
            continue                               # "BLITZ 1 — ...", "0:00 — KIRISH" kabi sarlavhalar
        if l.startswith("#"):
            continue
        ends = (".", "!", "?", "…", ":", ";", "»", '"', "”", ",")
        if len(l) < 70 and not l.endswith(ends) and (not prev or prev.endswith(ends[:4])):
            continue                               # alohida turgan qisqa sarlavha qatori (gap emas)
        keep.append(l.replace("**", ""))
        prev = l
    text = " ".join(x if x else "\n" for x in keep)
    text = re.sub(r"-\s+\n?\s*(?=[a-zʻ‘’'])", "", text)  # bo'g'in ko'chirishni tiklash
    text = re.sub(r"[ \t]+", " ", text)
    text = SPOKEN_BLITZ_RE.sub("", text)          # "Blitz bir." kabi so'zlarni o'qimaymiz
    return re.sub(r"\s*\n\s*", " ", text).strip()


def build(raw_text: str, note: str = "") -> dict:
    text = clean_text(raw_text)
    sents = tts.sentences(text)
    if len(sents) < 5:
        raise RuntimeError("Ssenariydan o'qiladigan matn topilmadi")
    numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(sents))
    data = llm.json_object(
        "Quyida YouTube video uchun TAYYOR ssenariy, gaplarga ajratilib raqamlangan. "
        "Matnni o'zgartirma va qayta yozma. Vazifang: mazmunga qarab 6-10 ta bo'limga ajrat — "
        "har bir bo'lim qaysi gap raqamidan boshlanishini 'start' da ko'rsat (birinchisi 0, "
        "o'sib boruvchi). Har bir bo'limga qisqa o'zbekcha sarlavha ber. Sarlavhalarda "
        "'Blitz' so'zini ishlatma. Shuningdek video sarlavhasi, tavsif va teglarni yoz."
        + (f"\nAdmin izohi: {note}" if note else "") + f"\n\n{numbered}",
        SEGMENT_SCHEMA, max_tokens=4096)
    starts = sorted({int(s.get("start", 0)) for s in data.get("sections", [])
                     if 0 <= int(s.get("start", 0)) < len(sents)} | {0})
    heads = {int(s.get("start", 0)): s.get("heading", "") for s in data.get("sections", [])}
    sections = []
    for k, st in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(sents)
        sid = "kirish" if k == 0 else ("yakun" if k == len(starts) - 1 else f"qism_{k}")
        sections.append({"id": sid, "heading": (heads.get(st) or "").strip() or data.get("book_title", ""),
                         "narration": " ".join(sents[st:end]), "image_prompt": ""})
    data["sections"] = sections
    for key, default in (("book_title", "Kitob"), ("author", ""), ("thumbnail_text", "10 DAQIQADA"),
                         ("thumbnail_prompt", "an open book glowing with warm golden light"),
                         ("description", ""), ("tags", [])):
        data.setdefault(key, default)
    data.setdefault("video_title", f"«{data['book_title']}» 10 daqiqada | UzBooks")
    data["mode"] = "tayyor ssenariy (so'zma-so'z)"
    return data
