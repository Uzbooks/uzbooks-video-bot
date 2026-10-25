"""Matn modeli: Google Gemini (bepul tarifda ishlaydi, GEMINI_API_KEY bilan).

Kitobni o'qish, ssenariy yozish va sifat nazorati shu modul orqali bajariladi.
Bepul tarifda daqiqasiga so'rovlar soni cheklangan, shuning uchun 429 xatosida
kutib, qayta urinadi.
"""
import json
import re
import time

from . import config

_client = None


def _get_client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=config.GEMINI_API_KEY())
    return _client


def _call(prompt: str, system: str | None, json_mode: bool, max_tokens: int) -> str:
    from google.genai import types

    cfg = types.GenerateContentConfig(
        system_instruction=system,
        max_output_tokens=max_tokens,
        temperature=0.7,
        response_mime_type="application/json" if json_mode else None,
    )
    last = None
    models = _ensure_models()
    while models:
        model = models[0]
        for attempt in range(4):
            try:
                resp = _get_client().models.generate_content(
                    model=model, contents=prompt, config=cfg)
                text = resp.text or ""
                if not text.strip():
                    raise RuntimeError("Gemini bo'sh javob qaytardi")
                return text
            except Exception as e:
                last = e
                msg = str(e)
                if _daily_quota_hit(msg) or "NOT_FOUND" in msg or "404" in msg:
                    # Kunlik limit tugagan yoki model yo'q: qayta urinish limitni bekorga
                    # yeydi, shuning uchun darhol keyingi modelga o'tamiz.
                    print(f"  {model}: kunlik limit tugadi yoki model topilmadi, keyingisiga o'tamiz")
                    break
                # daqiqalik limit (429) yoki server band (5xx): kutib qayta urinamiz
                wait = 65 if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) else 20 * (attempt + 1)
                print(f"  {model} xatosi ({attempt+1}/4), {wait} s kutamiz: {msg[:150]}")
                time.sleep(wait)
        models.pop(0)
    raise RuntimeError(f"Barcha Gemini matn modellarining limiti tugadi. Oxirgi xato: {str(last)[:400]}")


def _daily_quota_hit(msg: str) -> bool:
    m = msg.lower()
    return ("per day" in m or "perday" in m or "requests_per_day" in m
            or "retry in" in m and "h" in m.split("retry in", 1)[1][:12])


# Har bir modelning bepul limiti alohida. Biri tugasa, keyingisi ishlatiladi.
# Google eski modellarni vaqti-vaqti bilan o'chirib qo'yadi, shuning uchun ro'yxatni
# kalitingiz uchun hozir mavjud modellardan avtomatik tuzamiz.
_models: list[str] | None = None
_SKIP = ("image", "tts", "audio", "live", "embedding", "vision", "robotics", "computer-use")


def _version(name: str) -> float:
    m = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def _discover() -> list[str]:
    try:
        found = []
        for m in _get_client().models.list():
            name = (getattr(m, "name", "") or "").replace("models/", "")
            actions = getattr(m, "supported_actions", None) or []
            if actions and "generateContent" not in actions:
                continue
            if "gemini" not in name or "flash" not in name or any(k in name for k in _SKIP):
                continue
            found.append(name)
        # yangi versiyalar oldin; barqaror (preview emas) modellar oldin
        found.sort(key=lambda n: (-_version(n), "preview" in n or "exp" in n, "lite" in n, n))
        print(f"  Mavjud Gemini matn modellari: {', '.join(found[:8])}")
        return found
    except Exception as e:
        print(f"  Modellar ro'yxatini olib bo'lmadi: {str(e)[:150]}")
        return []


def _ensure_models() -> list[str]:
    global _models
    if _models is None:
        user = [config.TEXT_MODEL] if config.TEXT_MODEL else []
        extra = [m.strip() for m in config.TEXT_MODEL_FALLBACKS.split(",") if m.strip()]
        _models = list(dict.fromkeys(user + _discover() + extra))
    return _models


def text(prompt: str, system: str | None = None, max_tokens: int = 8192) -> str:
    return _call(prompt, system, json_mode=False, max_tokens=max_tokens)


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if m:
        raw = m.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    return json.loads(raw[start:end + 1])


def json_object(prompt: str, schema_hint: str, system: str | None = None,
                max_tokens: int = 16384) -> dict:
    """Modeldan JSON obyekt oladi. schema_hint — kerakli tuzilish tavsifi."""
    full = (f"{prompt}\n\nJavobni FAQAT quyidagi tuzilishdagi bitta JSON obyekt "
            f"ko'rinishida qaytar, boshqa hech narsa yozma:\n{schema_hint}")
    last = None
    for _ in range(3):
        raw = _call(full, system, json_mode=True, max_tokens=max_tokens)
        try:
            return _parse_json(raw)
        except Exception as e:  # buzilgan JSON bo'lsa qayta so'raymiz
            last = e
    raise RuntimeError(f"Gemini to'g'ri JSON qaytarmadi: {last}")
