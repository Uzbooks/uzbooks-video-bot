"""UzBooks avtomatik video zavodi.

Buyruqlar:
  python -m src.main collect              # Telegramdan yangi kitoblarni navbatga olish
  python -m src.main produce              # navbatdagi keyingi kitobdan video yasash va yuklash
  python -m src.main produce --file X.pdf # lokal faylni sinash (navbatsiz)
  python -m src.main produce --file X.pdf --no-upload   # YouTubega yuklamasdan
"""
import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path

from . import book_reader, compose, config, images, qa, script_writer, stock, telegram_io, tts, video


def build_video(book_path: Path, note: str, work: Path, upload: bool, notify: bool) -> dict:
    log = print
    work.mkdir(parents=True, exist_ok=True)

    # 1. Kitobni o'qish va o'rganish
    log("📖 Kitob o'qilmoqda...")
    text = book_reader.read_book(book_path)
    notes = script_writer.study_book(text)
    (work / "notes.md").write_text(notes, encoding="utf-8")

    # 2. Ssenariy + sifat nazorati (2 martagacha qayta yozish)
    feedback, script, review, formal = "", None, {}, []
    for attempt in range(3):
        log(f"✍️ Ssenariy yozilmoqda (urinish {attempt+1})...")
        script = script_writer.write_script(notes, note, feedback)
        formal = qa.check_script(script)
        review = qa.review_script(script, notes)
        if not formal and not review["critical"] and review["score"] >= 7:
            break
        feedback = "\n".join(formal + review["critical"] + review["minor"][:5])
    script_writer.save(script, work / "script.json")
    script_ok = not formal and not review["critical"]

    sections = script["sections"]

    # 3. Ovoz (har bir gap alohida — subtitrlar aniq tushishi uchun)
    log(f"🎙 Ovoz yozilmoqda ({tts.provider()})...")
    durations, all_cues = [], []
    for i, s in enumerate(sections):
        d, cues = tts.synthesize_with_cues(s["narration"], work / f"audio_{i}.mp3")
        durations.append(d)
        all_cues.append(cues)
    total_sec = sum(durations)

    # 4. Muqova
    thumb_raw, _ = images.make(script["thumbnail_prompt"], work / "thumb_raw.jpg", seed=99)
    thumb = video.make_thumbnail(thumb_raw, work / "thumbnail.jpg", script["thumbnail_text"])

    # 5. Sahnalar: stok video (Pexels) -> Gemini rasm -> bepul kartochka
    log("🎬 Sahnalar va montaj...")
    bar = compose.bar_png(work / "bar.png")
    segs, offset, gemini_used, stock_count, scene_total = [], 0.0, [], 0, 0
    for i, s in enumerate(sections):
        sec_dir = work / f"sec_{i}"
        sec_dir.mkdir(exist_ok=True)
        dur = durations[i]
        n = max(1, round(dur / config.SCENE_SECONDS))
        queries = [q for q in (s.get("broll") or []) if isinstance(q, str) and q.strip()]
        if not queries:
            queries = [" ".join(s["image_prompt"].split()[:4])]
        lengths = [dur / n] * n
        fallback_img = None
        parts = []
        for k in range(n):
            scene_total += 1
            clip = stock.fetch(queries[k % len(queries)], sec_dir / f"stock_{k}.mp4")
            if clip:
                stock_count += 1
                parts.append(compose.scene_from_video(clip, lengths[k], sec_dir / f"scene_{k}.mp4"))
                continue
            if fallback_img is None:
                num = int(s["id"].split("_")[1]) if s["id"].startswith("blitz_") else None
                fallback_img, ok_ai = images.make(s["image_prompt"], sec_dir / "img.jpg", seed=i, number=num)
                gemini_used.append(ok_ai)
            parts.append(compose.scene_from_image(fallback_img, lengths[k], sec_dir / f"scene_{k}.mp4", variant=i + k))
        visual = compose.join_video(parts, sec_dir / "visual.mp4")

        if s["id"].startswith("blitz_"):
            label, big = f"BLITZ {s['id'].split('_')[1]}", f"BLITZ {s['id'].split('_')[1]}"
        elif s["id"] == "kirish":
            label, big = "", script["book_title"]
        else:
            label, big = "XULOSA", "XULOSA"
        small = s["heading"] if s["id"] != "kirish" else script["author"]
        header = compose.header_png(sec_dir / "header.png", label, s["heading"])
        title = compose.title_card_png(sec_dir / "title.png", big, small)
        ass = compose.write_ass(all_cues[i], sec_dir / "subs.ass")
        segs.append(compose.render_section(visual, work / f"audio_{i}.mp3", dur, ass, header,
                                           title, bar, offset, total_sec, work / f"seg_{i}.mp4"))
        offset += dur
        log(f"  {i+1}/{len(sections)} bo'lim tayyor ({n} sahna)")
    final = video.concat(segs, work / "video.mp4")
    total = tts.duration(final)
    raw_imgs = [p for p in work.glob("sec_*/img.jpg")]

    # 6. Media sifat nazorati
    media_problems = qa.check_media(durations, total, raw_imgs)

    description = (f"{script['description']}\n\n⏱ Bo'limlar:\n"
                   f"{video.chapters(script, durations)}\n\n"
                   f"📚 Kitob: {script['book_title']} — {script['author']}\n"
                   f"Bu video kitobning qisqacha mazmuni. To'liq tajriba uchun kitobni o'qing!\n\n"
                   + (("🎥 Videolar: " + ", ".join(sorted(stock.sources)) + " — "
                       + ", ".join(sorted(set(stock.credits.values()))[:15]) + "\n\n")
                      if stock.credits else "")
                   + " ".join("#" + t.replace(" ", "") for t in script["tags"][:5]))
    (work / "description.txt").write_text(description, encoding="utf-8")

    result = {"title": script["video_title"], "minutes": round(total / 60, 1),
              "score": review.get("score"), "critical": review.get("critical", []),
              "minor": review.get("minor", []), "formal": formal,
              "media": media_problems, "video_id": None, "thumb_err": None,
              "voice": tts.provider(),
              "visuals": f"stok video {stock_count}/{scene_total} sahna"
                         + ("" if stock_count == scene_total else
                            (", qolgani Gemini rasm" if gemini_used and all(gemini_used)
                             else ", qolgani bepul kartochka"))}

    ok = script_ok and not media_problems
    yt_ready = bool(config.env("YT_REFRESH_TOKEN"))
    if upload and ok and not yt_ready:
        result["no_youtube"] = True
    if upload and ok and yt_ready:
        from . import youtube
        log("⬆️ YouTubega yuklanmoqda (private)...")
        vid, terr = youtube.upload(final, thumb, script["video_title"], description, script["tags"])
        result.update(video_id=vid, thumb_err=terr)

    if notify:
        report(result, thumb, work, ok)
    (work / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def report(r: dict, thumb: Path, work: Path, ok: bool) -> None:
    lines = [f"🎬 {r['title']}", f"⏱ {r['minutes']} daqiqa | ⭐ Sifat bahosi: {r['score']}/10",
             f"🎙 Ovoz: {r['voice']} | 🎥 Vizual: {r['visuals']}"]
    if r["video_id"]:
        lines += ["", "✅ YouTubega YOPIQ (private) holatda yuklandi.",
                  f"Ko'rib chiqing va chiqarish vaqtini belgilang:",
                  f"https://studio.youtube.com/video/{r['video_id']}/edit"]
        if r["thumb_err"]:
            lines.append("⚠️ Muqovani avtomatik qo'yib bo'lmadi — Studio'da qo'lda yuklang (fayl quyida).")
    elif not ok:
        lines += ["", "❌ Sifat nazoratidan o'tmadi, YouTubega yuklanmadi."]
    if r.get("no_youtube") or not r["video_id"]:
        run = run_url()
        if run:
            lines += ["", "📥 Videoni shu yerdan yuklab oling (Artifacts bo'limi, 7 kun saqlanadi):", run]
        if r.get("no_youtube"):
            lines.append("ℹ️ YouTube hali ulanmagan (YT_* kalitlar yo'q), shuning uchun yuklanmadi.")
    probs = r["formal"] + r["critical"] + r["media"]
    if probs:
        lines += ["", "Muammolar:"] + [f"• {p}" for p in probs]
    if r["minor"]:
        lines += ["", "Mayda eslatmalar:"] + [f"• {p}" for p in r["minor"][:5]]
    msg = "\n".join(lines)
    telegram_io.send_photo(thumb, r["title"])
    telegram_io.send(msg)
    telegram_io.send_document(work / "script.json", "Ssenariy")


def run_url() -> str:
    import os
    srv, repo, rid = (os.environ.get(k, "") for k in
                      ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    return f"{srv}/{repo}/actions/runs/{rid}" if repo and rid else ""


def produce_from_queue(upload: bool) -> int:
    telegram_io.collect()
    q = telegram_io.load_queue()
    pending = telegram_io.pending_books(q)
    if not pending:
        telegram_io.send("📭 Navbatda kitob yo'q — bugun video chiqmaydi. "
                         "Botga yangi kitob yuboring.")
        return 0
    book = pending[0]
    book["status"] = "processing"
    telegram_io.save_queue(q)
    work = config.WORK / book["id"]
    try:
        telegram_io.send(f"⚙️ «{book['file_name']}» bo'yicha video tayyorlanmoqda "
                         f"(taxminan 20–30 daqiqa)...")
        path = telegram_io.download(book["file_id"], work / ("book" + Path(book["file_name"]).suffix.lower()))
        res = build_video(path, book.get("note", ""), work, upload=upload, notify=True)
        book["status"] = "done" if (res["video_id"] or res.get("no_youtube") or not upload) else "needs_review"
        book["video_id"] = res["video_id"]
    except Exception as e:
        book["status"] = "failed" if book.get("tries", 0) >= 1 else "failed_retry"
        book["tries"] = book.get("tries", 0) + 1
        book["error"] = str(e)[:300]
        telegram_io.send(f"❌ «{book['file_name']}»: xatolik yuz berdi.\n{str(e)[:800]}")
        traceback.print_exc()
        return 1
    finally:
        telegram_io.save_queue(q)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["collect", "produce"])
    ap.add_argument("--file")
    ap.add_argument("--note", default="")
    ap.add_argument("--no-upload", action="store_true")
    a = ap.parse_args()
    if a.command == "collect":
        n = telegram_io.collect()
        print(f"Navbatga qo'shildi: {n}")
        return 0
    if a.file:
        src = Path(a.file)
        work = config.WORK / ("local_" + src.stem)
        res = build_video(src, a.note, work, upload=not a.no_upload, notify=False)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        print(f"Natija: {work}")
        return 0
    return produce_from_queue(upload=not a.no_upload)


if __name__ == "__main__":
    sys.exit(main())
