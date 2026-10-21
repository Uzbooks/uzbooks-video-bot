"""Gemini (Nano Banana) orqali rasm yaratish."""
import io
import time
from pathlib import Path

from PIL import Image

from . import config


def _style() -> str:
    return (config.PROMPTS / "image_style.txt").read_text(encoding="utf-8").strip()


def fit_16x9(img: Image.Image) -> Image.Image:
    """Rasmni 1920x1080 ga kesib moslaydi."""
    W, H = config.VIDEO_W, config.VIDEO_H
    img = img.convert("RGB")
    scale = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    left = (img.width - W) // 2
    top = (img.height - H) // 2
    return img.crop((left, top, left + W, top + H))


def generate(prompt: str, dest: Path, retries: int = 3) -> Path:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=config.GEMINI_API_KEY())
    full = f"{prompt}\n\n{_style()}"
    last_err = None
    for attempt in range(retries):
        try:
            try:
                cfg = types.GenerateContentConfig(
                    response_modalities=["IMAGE"],
                    image_config=types.ImageConfig(aspect_ratio="16:9"))
            except Exception:  # eski SDK versiyasi
                cfg = types.GenerateContentConfig(response_modalities=["IMAGE"])
            resp = client.models.generate_content(
                model=config.GEMINI_IMAGE_MODEL, contents=full, config=cfg)
            for part in resp.candidates[0].content.parts:
                if getattr(part, "inline_data", None) and part.inline_data.data:
                    img = Image.open(io.BytesIO(part.inline_data.data))
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    fit_16x9(img).save(dest, quality=95)
                    return dest
            raise RuntimeError("Gemini rasm qaytarmadi")
        except Exception as e:  # tarmoq / limit xatolari
            last_err = e
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"Rasm yaratilmadi: {last_err}")


# ---------------- Bepul variant: dizayn-kartochka (API'siz) ----------------
NAVY = (15, 27, 61)
NAVY2 = (28, 45, 96)
GOLD = (242, 179, 61)
CORAL = (242, 107, 58)


def card(seed: int, dest: Path, number: int | None = None) -> Path:
    """Gemini rasmi o'rniga kanal uslubidagi chiroyli fon yasaydi (pul talab qilmaydi).
    Har bir bo'limda shakllar joylashuvi biroz farq qiladi."""
    import random
    from PIL import ImageChops, ImageDraw, ImageFilter

    W, H = config.VIDEO_W, config.VIDEO_H
    rnd = random.Random(seed * 7919 + 13)
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    for y in range(H):  # yuqoridan pastga gradient
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(NAVY2[c] * (1 - t) + NAVY[c] * t) for c in range(3)))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    for _ in range(5):  # yumshoq yorug' doiralar
        r = rnd.randint(160, 420)
        x, y = rnd.randint(W // 2, W), rnd.randint(0, H)
        col = GOLD if rnd.random() < 0.6 else CORAL
        g.ellipse([x - r, y - r, x + r, y + r], fill=tuple(int(c * 0.55) for c in col))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = ImageChops.screen(img, glow)
    d = ImageDraw.Draw(img)
    for _ in range(3):  # ingichka halqalar
        r = rnd.randint(120, 300)
        x, y = rnd.randint(int(W * 0.55), W - 300), rnd.randint(320, H - 320)
        d.ellipse([x - r, y - r, x + r, y + r], outline=GOLD, width=3)
    if number:  # katta bo'lim raqami
        from .video import font
        d.text((W - 160, H // 2 - 120), str(number), font=font(420), fill=GOLD, anchor="rm")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, quality=95)
    return dest


_gemini_failed = False


def make(prompt: str, dest: Path, seed: int, number: int | None = None) -> tuple[Path, bool]:
    """Sozlamaga qarab rasm yasaydi. (yo'l, gemini_ishladimi) qaytaradi."""
    global _gemini_failed
    mode = config.IMAGE_PROVIDER
    if mode == "cards" or (mode == "auto" and _gemini_failed):
        return card(seed, dest, number), False
    try:
        return generate(prompt, dest, retries=3 if mode == "gemini" else 2), True
    except Exception as e:
        if mode == "gemini":
            raise
        print(f"  Gemini rasm ishlamadi, bepul kartochkaga o'tamiz: {str(e)[:200]}")
        _gemini_failed = True
        return card(seed, dest, number), False
