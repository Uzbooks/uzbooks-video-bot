"""Haqiqiy video montaj: har bir bo'lim bir nechta sahnadan iborat
(stok video yoki harakatlanuvchi rasm), ustida subtitrlar, bo'lim sarlavhasi,
kirish kartochkasi va pastda progress-bar."""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from . import config
from .video import GOLD, NAVY, WHITE, _wrap, font

W, H, FPS = config.VIDEO_W, config.VIDEO_H, config.FPS
SUB_FONT = "DejaVu Sans"   # o'zbekcha ʻ belgilarini to'liq qo'llab-quvvatlaydi
ENC = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def disp(text: str) -> str:
    """Ekranda chiroyli ko'rinishi uchun apostroflarni almashtiramiz."""
    return text.replace("ʻ", "‘").replace("ʼ", "’")


def _run(cmd: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *cmd], check=True)


# ---------------- sahnalar ----------------
def scene_from_video(src: Path, seconds: float, dest: Path) -> Path:
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
          f"fps={FPS},eq=brightness=-0.05:saturation=0.92,"
          f"fade=t=in:st=0:d=0.35")
    _run(["-stream_loop", "-1", "-i", str(src), "-t", f"{seconds:.3f}", "-an",
          "-vf", vf, *ENC, str(dest)])
    return dest


def scene_from_image(src: Path, seconds: float, dest: Path, variant: int) -> Path:
    """Rasmni jonlantiradi: navbat bilan zoom-in, zoom-out va yon tomonga siljish."""
    frames = int(seconds * FPS) + 1
    step = 0.12 / frames
    mode = variant % 3
    if mode == 0:
        z, x, y = f"1+{step:.8f}*on", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif mode == 1:
        z, x, y = f"1.12-{step:.8f}*on", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    else:
        z, x, y = "1.12", f"(iw-iw/zoom)*on/{frames}", "ih/2-(ih/zoom/2)"
    vf = (f"scale={W*2}:{H*2},zoompan=z='{z}':d={frames}:x='{x}':y='{y}':s={W}x{H}:fps={FPS},"
          f"setsar=1,fade=t=in:st=0:d=0.35")
    _run(["-loop", "1", "-framerate", str(FPS), "-i", str(src), "-t", f"{seconds:.3f}",
          "-vf", vf, *ENC, str(dest)])
    return dest


def join_video(parts: list[Path], dest: Path) -> Path:
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    _run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dest)])
    return dest


# ---------------- grafika qatlamlari (shaffof PNG) ----------------
def header_png(dest: Path, label: str, heading: str) -> Path:
    """Doimiy qatlam: chap yuqorida bo'lim nomi, o'ng yuqorida kanal nomi, pastda progress yo'lagi foni."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f_lab, f_head = font(30), font(34)
    x, y = 60, 50
    text = disp(heading if len(heading) <= 48 else heading[:46] + "…")
    if label:
        lw = d.textlength(label, font=f_lab)
        d.rounded_rectangle([x, y, x + lw + 32, y + 50], radius=10, fill=GOLD + (255,))
        d.text((x + 16, y + 8), label, font=f_lab, fill=NAVY)
        x += lw + 48
    hw = d.textlength(text, font=f_head)
    d.rounded_rectangle([x - 6, y, x + hw + 30, y + 50], radius=10, fill=(5, 10, 25, 150))
    d.text((x + 12, y + 5), text, font=f_head, fill=WHITE)
    d.text((W - 60, y + 4), config.CHANNEL_NAME, font=font(38), fill=GOLD + (255,), anchor="ra")
    d.rectangle([0, H - 10, W, H], fill=(0, 0, 0, 110))
    img.save(dest)
    return dest


def title_card_png(dest: Path, big: str, small: str) -> Path:
    """Bo'lim boshida 3 soniya ko'rinadigan katta sarlavha."""
    img = Image.new("RGBA", (W, H), (5, 10, 25, 175))
    d = ImageDraw.Draw(img)
    size = 150
    while size > 60 and d.textlength(disp(big), font=font(size)) > W * 0.9:
        size -= 10
    fb = font(size)
    d.text((W // 2, H // 2 - 70), disp(big), font=fb, fill=GOLD + (255,), anchor="mm")
    fs = font(64)
    lines = _wrap(d, disp(small), fs, W * 0.75)[:2]
    y = H // 2 + 50
    for ln in lines:
        d.text((W // 2, y), ln, font=fs, fill=WHITE, anchor="ma")
        y += 80
    d.line([(W // 2 - 120, H // 2 + 25), (W // 2 + 120, H // 2 + 25)], fill=GOLD, width=5)
    img.save(dest)
    return dest


def bar_png(dest: Path) -> Path:
    Image.new("RGBA", (W, 10), GOLD + (255,)).save(dest)
    return dest


# ---------------- subtitrlar (ASS) ----------------
def _ts(t: float) -> str:
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _chunks(text: str, max_chars: int = 84) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars and cur:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


def write_ass(cues: list[tuple[float, float, str]], dest: Path) -> Path:
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{SUB_FONT},54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,4,1,2,160,160,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for start, end, text in cues:
        parts = _chunks(text)
        total = sum(len(p) for p in parts) or 1
        t = start
        for p in parts:  # uzun gapni bo'laklarga bo'lib, vaqtni harf soniga qarab taqsimlaymiz
            d = (end - start) * len(p) / total
            safe = p.replace("{", "(").replace("}", ")").replace("\n", " ")
            lines.append(f"Dialogue: 0,{_ts(t)},{_ts(t + d)},Sub,,0,0,0,,{safe}")
            t += d
    dest.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    return dest


def _esc(p: Path) -> str:
    return str(p.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


# ---------------- bo'limni yig'ish ----------------
def render_section(visual: Path, audio: Path, seconds: float, ass: Path, header: Path,
                   title: Path, bar: Path, offset: float, total: float, dest: Path) -> Path:
    """visual — sahnalardan yig'ilgan ovozsiz video. Ustiga barcha qatlamlarni qo'yadi."""
    fade_out = max(seconds - 0.4, 0)
    fc = (
        f"[0:v][2:v]overlay=0:0[a];"
        f"[3:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st=2.6:d=0.5:alpha=1[tc];"
        f"[a][tc]overlay=0:0:enable='lt(t,3.2)'[b];"
        f"[b][4:v]overlay=x='-w+w*({offset:.3f}+t)/{total:.3f}':y=H-h[c];"
        f"[c]subtitles='{_esc(ass)}'[d];"
        f"[d]fade=t=in:st=0:d=0.3,fade=t=out:st={fade_out:.2f}:d=0.4[v]"
    )
    _run(["-i", str(visual), "-i", str(audio),
          "-loop", "1", "-i", str(header), "-loop", "1", "-i", str(title),
          "-loop", "1", "-i", str(bar),
          "-filter_complex", fc, "-map", "[v]", "-map", "1:a",
          "-t", f"{seconds:.3f}", *ENC, "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
          str(dest)])
    return dest
