"""Rasm + audio → MP4 video (sekin zoom effekti bilan), muqova (thumbnail) yasash."""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config

FONT_CANDIDATES = [
    config.ROOT / "fonts" / "Montserrat-ExtraBold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]
GOLD = (242, 179, 61)
WHITE = (255, 255, 255)
NAVY = (15, 27, 61)


def font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


def _wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=fnt) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _left_gradient(img: Image.Image, strength: int = 210, width_ratio: float = 0.62) -> Image.Image:
    W, H = img.size
    grad = Image.new("L", (W, 1))
    gw = int(W * width_ratio)
    for x in range(W):
        grad.putpixel((x, 0), int(strength * max(0, 1 - x / gw)) if x < gw else 0)
    mask = grad.resize((W, H))
    dark = Image.new("RGB", (W, H), NAVY)
    return Image.composite(dark, img, mask)


def overlay_frame(src: Path, dest: Path, label: str, heading: str) -> Path:
    """Video kadri: pastki-chap burchakda 'BLITZ 3' va sarlavha, yuqorida kanal nomi."""
    img = Image.open(src).convert("RGB")
    W, H = img.size
    # pastdan yumshoq qoraytirish
    shade = Image.new("L", (W, H), 0)
    sd = ImageDraw.Draw(shade)
    for y in range(int(H * 0.55), H):
        sd.line([(0, y), (W, y)], fill=int(200 * (y - H * 0.55) / (H * 0.45)))
    img = Image.composite(Image.new("RGB", (W, H), (5, 10, 25)), img, shade)
    d = ImageDraw.Draw(img)
    x0, y_bottom = 90, H - 90
    f_head, f_label = font(64), font(34)
    lines = _wrap(d, heading, f_head, W * 0.62)[:2]
    y = y_bottom - len(lines) * 78
    if label:
        tw = d.textlength(label, font=f_label)
        d.rounded_rectangle([x0, y - 70, x0 + tw + 40, y - 18], radius=10, fill=GOLD)
        d.text((x0 + 20, y - 64), label, font=f_label, fill=NAVY)
    for ln in lines:
        d.text((x0, y), ln, font=f_head, fill=WHITE)
        y += 78
    d.text((W - 90, 60), config.CHANNEL_NAME, font=font(36), fill=GOLD, anchor="ra")
    img.save(dest, quality=95)
    return dest


def make_thumbnail(src: Path, dest: Path, text: str) -> Path:
    img = Image.open(src).convert("RGB").resize((1280, 720), Image.LANCZOS)
    img = _left_gradient(img, strength=225, width_ratio=0.7)
    d = ImageDraw.Draw(img)
    size = 118
    while size > 60:
        f = font(size)
        lines = _wrap(d, text.upper(), f, 700)
        if len(lines) <= 3:
            break
        size -= 8
    y = 360 - len(lines) * (size + 12) // 2
    for ln in lines:
        # qora soya (o'qilishi uchun)
        for dx, dy in ((5, 5), (3, 3)):
            d.text((60 + dx, y + dy), ln, font=f, fill=(0, 0, 0))
        d.text((60, y), ln, font=f, fill=(255, 214, 10))
        y += size + 12
    badge_f = font(40)
    label = "10 DAQIQADA"
    tw = d.textlength(label, font=badge_f)
    d.rounded_rectangle([60, 600, 60 + tw + 44, 664], radius=14, fill=(242, 107, 58))
    d.text((82, 609), label, font=badge_f, fill=WHITE)
    d.text((1230, 40), config.CHANNEL_NAME, font=font(40), fill=GOLD, anchor="ra")
    img.save(dest, quality=92)
    if dest.stat().st_size > 2_000_000:  # YouTube limiti 2 MB
        img.save(dest, quality=80)
    return dest


def render_segment(image: Path, audio: Path, seconds: float, dest: Path, zoom_in: bool = True) -> Path:
    frames = int(seconds * config.FPS) + 1
    W, H = config.VIDEO_W, config.VIDEO_H
    step = 0.10 / frames  # butun bo'lim davomida ~10% zoom
    z = f"min(1+{step:.8f}*on,1.10)" if zoom_in else f"max(1.10-{step:.8f}*on,1.0)"
    vf = (f"scale={W*2}:{H*2},zoompan=z='{z}':d={frames}:"
          f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={config.FPS},"
          f"fade=t=in:st=0:d=0.5,fade=t=out:st={max(seconds-0.5,0):.2f}:d=0.5,format=yuv420p")
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", str(config.FPS),
        "-i", str(image), "-i", str(audio), "-vf", vf, "-t", f"{seconds:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-shortest", str(dest)], check=True)
    return dest


def concat(segments: list[Path], dest: Path) -> Path:
    lst = dest.with_suffix(".txt")
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in segments))
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(lst), "-c", "copy", "-movflags", "+faststart", str(dest)], check=True)
    return dest


def chapters(script: dict, durations: list[float]) -> str:
    """YouTube bo'limlari (vaqt belgilari) — tavsifga qo'yiladi."""
    t, out = 0.0, []
    for s, d in zip(script["sections"], durations):
        m, sec = divmod(int(t), 60)
        out.append(f"{m}:{sec:02d} {s['heading']}")
        t += d
    return "\n".join(out)
