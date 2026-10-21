"""Kitobni o'rganish va UzBooks ssenariysini yozish (Gemini matn modeli, bepul)."""
import json
import time

from . import config, llm
from .book_reader import chunks

SECTION_IDS = ["kirish"] + [f"blitz_{i}" for i in range(1, config.BLITZ_COUNT + 1)] + ["yakun"]

SCRIPT_SCHEMA = """{
  "book_title": "kitob nomi o'zbekcha (asl nomi qavsda bo'lishi mumkin)",
  "author": "muallif",
  "video_title": "«Kitob nomi» 10 daqiqada | Muallif | UzBooks  (70 belgigacha)",
  "thumbnail_text": "muqova uchun 2-4 so'z",
  "thumbnail_prompt": "muqova rasmi uchun inglizcha tavsif, matnsiz",
  "description": "YouTube tavsifi o'zbekcha, 3-5 gap",
  "tags": ["8-15 ta teg"],
  "sections": [
    {"id": "kirish | blitz_1 ... blitz_7 | yakun",
     "heading": "ekranda chiqadigan qisqa sarlavha o'zbekcha (45 belgigacha)",
     "narration": "ovoz uchun to'liq matn",
     "image_prompt": "shu bo'lim uchun inglizcha rasm tavsifi, matnsiz, metafora orqali"}
  ]
}"""

REQUIRED_KEYS = ["book_title", "author", "video_title", "thumbnail_text",
                 "thumbnail_prompt", "description", "tags", "sections"]


def study_book(book_text: str) -> str:
    """Kitobni o'qib, batafsil konspekt tayyorlaydi. Uzun kitoblar bo'laklab o'qiladi."""
    parts = chunks(book_text)
    notes = []
    for i, part in enumerate(parts, 1):
        if i > 1:
            time.sleep(60)  # bepul tarifning daqiqalik token limitiga sig'ish uchun
        notes.append(llm.text(
            f"Quyida kitobning {i}/{len(parts)}-qismi. Uni diqqat bilan o'qib, "
            "batafsil konspekt yoz (o'zbek tilida): asosiy g'oyalar, har bir g'oyaning "
            "dalillari, muallif keltirgan eng yorqin misollar va hikoyalar, aniq "
            "raqamlar/tadqiqotlar (faqat kitobda bor bo'lsa), kitob nomi va muallif. "
            "Faqat kitobdagi ma'lumotga tayan.\n\n<kitob>\n" + part + "\n</kitob>"))
    if len(notes) == 1:
        return notes[0]
    time.sleep(60)
    return llm.text(
        "Quyida bitta kitobning bo'laklari bo'yicha konspektlar. Ularni bitta "
        "yaxlit konspektga birlashtir: kitobning eng muhim 10-12 g'oyasi, "
        "misollar va dalillar bilan.\n\n" + "\n\n---\n\n".join(notes))


def write_script(notes: str, note: str = "", feedback: str = "") -> dict:
    style = (config.PROMPTS / "style.md").read_text(encoding="utf-8")
    example_path = config.PROMPTS / "example_script.md"
    example = example_path.read_text(encoding="utf-8") if example_path.exists() else ""
    prompt = (
        "Quyidagi kitob konspekti asosida UzBooks videosi uchun ssenariy yoz. "
        "Bo'limlar aynan shu tartibda bo'lsin: " + ", ".join(SECTION_IDS) +
        f". Kitobning eng muhim va eng amaliy {config.BLITZ_COUNT} ta g'oyasini tanla.\n\n"
        f"<konspekt>\n{notes}\n</konspekt>\n")
    if note:
        prompt += f"\nAdmin izohi: {note}\n"
    if example:
        prompt += (f"\n<namuna_ssenariy>\n{example}\n</namuna_ssenariy>\n"
                   "Uslub va hajm shu namunadek bo'lsin, mazmun esa yangi kitobdan.\n")
    if feedback:
        prompt += f"\nOldingi variantda sifat nazorati topgan kamchiliklar, ularni tuzat:\n{feedback}\n"

    data = llm.json_object(prompt, SCRIPT_SCHEMA, system=style)
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise RuntimeError(f"Ssenariyda maydonlar yetishmaydi: {missing}")
    order = {sid: i for i, sid in enumerate(SECTION_IDS)}
    data["sections"].sort(key=lambda s: order.get(s.get("id"), 99))
    return data


def save(script: dict, path) -> None:
    path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
