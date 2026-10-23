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
    for attempt in range(6):
        try:
            resp = _get_client().models.generate_content(
                model=config.TEXT_MODEL, contents=prompt, config=cfg)
            text = resp.text or ""
            if not text.strip():
                raise RuntimeError("Gemini bo'sh javob qaytardi")
            return text
        except Exception as e:
            last = e
            msg = str(e)
            # 429 = bepul limit, 500/503 = server band. Kutib qayta urinamiz.
            wait = 120 if ("429" in msg or "RESOURCE_EXHAUSTED" in msg or "503" in msg or "UNAVAILABLE" in msg) else 20 * (attempt + 1)
            print(f"  Gemini xatosi ({attempt+1}/6), {wait} s kutamiz: {msg[:150]}")
            time.sleep(wait)
    raise RuntimeError(f"Gemini matn modeli javob bermadi: {last}")


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
