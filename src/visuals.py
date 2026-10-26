"""Sahnalar: ovozdagi gaplarga qarab videoni ~10 soniyalik sahnalarga bo'lish va
har bir sahna uchun AYNAN o'sha gaplarda aytilgan narsani ko'rsatadigan rasm/video tanlash."""
import json

from . import config, llm

PLAN_SCHEMA = """{
  "look": "butun video uchun yagona vizual uslub va takrorlanadigan qahramonlar tavsifi (inglizcha, 1-2 gap)",
  "scenes": [{"i": 0, "prompt": "inglizcha rasm tavsifi", "query": "2-4 so'zli inglizcha stok-video qidiruvi"}]
}"""


def group_scenes(cues: list[tuple[float, float, str]], section_len: float) -> list[dict]:
    """Bo'lim ichidagi gaplarni sahnalarga birlashtiradi (sahna gap o'rtasida uzilmaydi)."""
    target = config.SCENE_SECONDS
    scenes, cur, start = [], [], 0.0
    for a, b, text in cues:
        if not cur:
            start = a if not scenes else scenes[-1]["end"]
        cur.append(text)
        if b - start >= target:
            scenes.append({"start": start, "end": b, "text": " ".join(cur)})
            cur = []
    if cur:
        if scenes and (cues[-1][1] - scenes[-1]["end"]) < target * 0.45:
            scenes[-1]["text"] += " " + " ".join(cur)      # juda qisqa qoldiq — oldingisiga qo'shamiz
        else:
            scenes.append({"start": scenes[-1]["end"] if scenes else 0.0, "end": 0, "text": " ".join(cur)})
    if not scenes:
        scenes = [{"start": 0.0, "end": section_len, "text": " ".join(c[2] for c in cues)}]
    scenes[0]["start"] = 0.0
    scenes[-1]["end"] = section_len                       # oxirgi sahna pauzani ham qoplaydi
    for k in range(len(scenes) - 1):
        scenes[k]["end"] = scenes[k + 1]["start"]
    for s in scenes:
        s["len"] = max(0.5, s["end"] - s["start"])
    return scenes


def plan(script: dict, all_scenes: list[dict]) -> str:
    """Bitta Gemini so'rovi bilan barcha sahnalar uchun rasm tavsifi va stok qidiruv so'zini yozadi."""
    numbered = "\n".join(f"[{i}] {s['text']}" for i, s in enumerate(all_scenes))
    try:
        data = llm.json_object(
            "Sen hujjatli film rejissyorisan. Quyida o'zbekcha video ovozi sahnalarga bo'lingan. "
            f"Kitob: «{script.get('book_title', '')}» — {script.get('author', '')}.\n"
            "Har bir sahna uchun shu sahnada AYNAN NIMA aytilayotganini ko'rsatadigan kadrni o'ylab top:\n"
            "- Hikoya bo'lsa — o'sha voqeani (odamlar, joy, davr, harakat) aniq tasvirla.\n"
            "- Mavhum g'oya bo'lsa — uni ko'rinadigan hayotiy vaziyat orqali ko'rsat (masalan, "
            "'qaror qabul qilish' -> chorrahada turgan odam), lekin mavzudan chetga chiqma.\n"
            "- Butun video bitta uslubda bo'lsin, takrorlanadigan qahramonlar bir xil ko'rinsin.\n"
            "- Rasmda yozuv, harf, raqam, logotip bo'lmasin.\n"
            "prompt — inglizcha, 25-60 so'z. query — stok videolar uchun 2-4 so'zli inglizcha "
            "qidiruv (aniq, suratga olinadigan narsa).\n"
            f"Sahnalar soni: {len(all_scenes)}. Har biri uchun 'i' raqamini saqla.\n\n{numbered}",
            PLAN_SCHEMA, max_tokens=16384)
        by_i = {int(s.get("i", -1)): s for s in data.get("scenes", [])}
        for i, s in enumerate(all_scenes):
            got = by_i.get(i, {})
            s["prompt"] = (got.get("prompt") or "").strip()
            s["query"] = (got.get("query") or "").strip()
        return (data.get("look") or "").strip()
    except Exception as e:
        print(f"  Sahna rejasini tuzib bo'lmadi: {str(e)[:200]}")
        return ""


def save_plan(all_scenes: list[dict], path) -> None:
    path.write_text(json.dumps(all_scenes, ensure_ascii=False, indent=1), encoding="utf-8")
