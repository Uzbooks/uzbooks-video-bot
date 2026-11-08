"""Ovoz dvijoklarini solishtirish: bir xil o'zbekcha matnni har xil ovozda o'qib, namunalarni beradi.

  python -m src.tts_test                                   # Edge (' va ʻ bilan) + Aisha
  python -m src.tts_test --providers edge_female,omnivoice  # boshqa ovozlar
  python -m src.tts_test --providers omnivoice --text "Salom, dunyo."
  python -m src.tts_test --telegram                        # namunalarni Telegramga yuborish (GitHub'da)

Har bir namuna uchun: tayyorlanish vaqti, RTF (1 dan kichik — real vaqtdan tez) va ovoz tekshiruvi.
"""
import argparse
import json
import time
from pathlib import Path

from . import audio_qa, config, tts_engines

SAMPLE = (
    "Assalomu alaykum, aziz do'stlar! Bugun biz Napoleon Xillning «O'ylang va boying» kitobi haqida "
    "gaplashamiz. Bu kitob 1937-yilda nashr etilgan va shu kungacha 100 million nusxadan ko'p sotilgan. "
    "G'oya oddiy: aniq maqsad, qat'iy reja va har kuni kichik qadam. O'zbekistonda ham, Germaniyada ham "
    "bu qoidalar bir xil ishlaydi. Muallif yigirma yil davomida Andrew Carnegie, Henry Ford va Thomas Edison "
    "kabi beshyuzdan ortiq muvaffaqiyatli insonlar bilan suhbatlashgan, ularning odatlarini o'rganib, "
    "ularni o'n uchta tamoyilga jamlagan. Sizningcha, eng muhimi qaysi? Soat 10:30 da boshlangan uchrashuv "
    "2,5 soat davom etdi, natijada sotuvlar 25% ga oshdi."
)

PRESETS = {
    "edge": ("edge", "uz-UZ-SardorNeural"),
    "edge_okina": ("edge", "uz-UZ-SardorNeural"),                    # oʻ/gʻ — ʻ belgisi bilan
    "aisha": ("aisha", ""),
    "edge_female": ("edge", "uz-UZ-MadinaNeural"),
    "omnivoice": ("omnivoice", ""),                                  # OMNIVOICE_VOICE (erkak)
    "omnivoice_female": ("omnivoice", "female, middle-aged, moderate pitch"),
    "elevenlabs": ("elevenlabs", ""),
}


def run(names: list[str], text: str, out: Path, telegram: bool) -> list[dict]:
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for key in names:
        if key not in PRESETS:
            print(f"Noma'lum: {key} (mumkin: {', '.join(PRESETS)})")
            continue
        name, voice = PRESETS[key]
        res = {"preset": key, "ok": False}
        try:
            eng = tts_engines.make(name, voice)
            if key == "edge_okina":
                eng.apostrophe = "ʻ"
            ok, why = eng.available()
            if not ok:
                res["error"] = f"NOT TESTED — {why}"
                print(f"[{key}] {res['error']}")
                results.append(res)
                continue
            dest = out / f"{key}.mp3"
            t0 = time.time()
            dur, cues = tts_engines.section(eng, text, dest)
            took = time.time() - t0
            _, warns, info = audio_qa.check(dest, len(text))
            res.update(ok=True, label=eng.label(), seconds=round(dur, 1), took=round(took, 1),
                       rtf=round(took / max(dur, 0.1), 2), sentences=len(cues), warnings=warns, **info)
            print(f"[{key}] OK: {dur:.1f} s audio, {took:.0f} s da (RTF {res['rtf']})")
            if telegram:
                from . import telegram_io
                telegram_io.send_document(dest, f"🎙 {eng.label()}\n⏱ {dur:.0f} s audio, {took:.0f} s da "
                                                f"tayyorlandi (RTF {res['rtf']})"
                                          + (f"\n⚠️ {'; '.join(warns)}" if warns else ""))
        except Exception as e:
            res["error"] = tts_engines._redact(str(e)[:400])
            print(f"[{key}] XATO: {res['error']}")
        results.append(res)
    (out / "report.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    if telegram:
        from . import telegram_io
        lines = ["🧪 Ovoz sinovi natijasi:"]
        for r in results:
            lines.append(f"• {r['preset']}: " + (f"✅ RTF {r['rtf']}, {r['seconds']} s" if r["ok"]
                                                  else f"❌ {r.get('error', '')[:200]}"))
        lines.append("\nQaysi biri tabiiyroq? Tanlovingizni TTS_PROVIDER ga yozing.")
        telegram_io.send("\n".join(lines))
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default=config.env("TTS_TEST_PROVIDERS",
                                                      "edge,edge_okina,aisha"))
    ap.add_argument("--text", default="")
    ap.add_argument("--out", default=str(config.WORK / "tts_test"))
    ap.add_argument("--telegram", action="store_true")
    a = ap.parse_args()
    run([x.strip() for x in a.providers.split(",") if x.strip()], a.text or SAMPLE, Path(a.out), a.telegram)
