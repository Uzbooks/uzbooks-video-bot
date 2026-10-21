"""Sifat nazorati: avtomatik tekshiruvlar + Claude muharrir ko'rigi."""
import json
import re

from . import config, llm
from .script_writer import SECTION_IDS

CYRILLIC = re.compile(r"[Ѐ-ӿ]")

REVIEW_SCHEMA = """{
  "score": 1-10 butun son (umumiy baho),
  "critical": ["jiddiy muammolar: kitobda yo'q faktlar, buzilgan g'oyalar, uzun iqtiboslar, noto'g'ri muallif yoki nom"],
  "minor": ["mayda kamchiliklar: imlo, uslub, takror"]
}"""


def word_count(s: str) -> int:
    return len(re.findall(r"\w+", s))


def check_script(script: dict) -> list[str]:
    """Kod orqali tekshiriladigan formal talablar. Muammolar ro'yxatini qaytaradi."""
    problems = []
    ids = [s["id"] for s in script["sections"]]
    if ids != SECTION_IDS:
        problems.append(f"Bo'limlar tartibi noto'g'ri: {ids}")
    full = " ".join(s["narration"] for s in script["sections"])
    wc = word_count(full)
    if not (config.WORDS_MIN <= wc <= config.WORDS_MAX):
        problems.append(f"Matn hajmi {wc} so'z (kerak: {config.WORDS_MIN}–{config.WORDS_MAX})")
    if CYRILLIC.search(full + script["video_title"]):
        problems.append("Matnda kirill harflari bor")
    if len(script["video_title"]) > 100:
        problems.append("Sarlavha 100 belgidan uzun (YouTube limiti)")
    for s in script["sections"]:
        if word_count(s["narration"]) < 60:
            problems.append(f"{s['id']} bo'limi juda qisqa")
    return problems


def review_script(script: dict, notes: str) -> dict:
    try:
        r = llm.json_object(
            "Sen qattiqqo'l muharrirsan. Ssenariyni kitob konspekti bilan solishtirib tekshir:\n"
            "1) Har bir fakt va g'oya konspektda bormi? To'qilgan raqam yoki tadqiqot yo'qmi?\n"
            "2) Kitob nomi va muallif to'g'rimi?\n"
            "3) So'zma-so'z uzun iqtiboslar yo'qmi?\n"
            "4) O'zbek tili imlosi (lotin), grammatika, ovozda tabiiy eshitiladimi?\n"
            "5) Ilgak qiziqarlimi, misollar hayotiymi?\n"
            "Muammo bo'lmasa, ro'yxatlarni bo'sh qoldir.\n\n"
            f"<konspekt>\n{notes}\n</konspekt>\n\n<ssenariy>\n"
            + json.dumps(script, ensure_ascii=False, indent=1) + "\n</ssenariy>",
            REVIEW_SCHEMA, max_tokens=4096)
        return {"score": int(r.get("score", 0)), "critical": list(r.get("critical") or []),
                "minor": list(r.get("minor") or [])}
    except Exception as e:
        return {"score": 0, "critical": [f"Sifat nazorati ishlamadi: {str(e)[:150]}"], "minor": []}


def check_media(sections_audio: list[float], video_seconds: float, images: list) -> list[str]:
    problems = []
    minutes = video_seconds / 60
    if not (config.TARGET_MINUTES_MIN <= minutes <= config.TARGET_MINUTES_MAX):
        problems.append(f"Video davomiyligi {minutes:.1f} daqiqa (kerak: "
                        f"{config.TARGET_MINUTES_MIN}–{config.TARGET_MINUTES_MAX})")
    for i, d in enumerate(sections_audio):
        if d < 15:
            problems.append(f"{i+1}-bo'lim audiosi juda qisqa ({d:.0f} s)")
    if any(not p.exists() for p in images):
        problems.append("Ba'zi rasmlar yaratilmadi")
    return problems
