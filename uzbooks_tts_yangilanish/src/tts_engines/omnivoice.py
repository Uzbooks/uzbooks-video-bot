"""OmniVoice (k2-fsa, Apache-2.0) — bepul, lokal, CPU'da ishlaydi. O'zbekcha (uz) rasmiy ro'yxatda bor.

SINOV BOSQICHIDA: o'zbekcha sifati hali tinglab tasdiqlanmagan. Avval `tts_test` bilan tekshiring.

Ovoz barqarorligi: ovoz bir marta tavsif (OMNIVOICE_VOICE) bo'yicha yaratiladi va "ovoz namunasi"
sifatida keshga saqlanadi — keyingi barcha gaplar va videolar shu ovoz bilan o'qiladi.
Har bir gap alohida o'qiladi, shuning uchun subtitr vaqtlari aniq (taxminiy emas).
"""
import hashlib
import inspect
import re
import time
import wave
from pathlib import Path

from .base import Engine, TTSError

SR = 24000
_model = None


def _split_long(sentence: str, limit: int = 260) -> list[str]:
    if len(sentence) <= limit:
        return [sentence]
    parts, cur = [], ""
    for piece in re.split(r"(?<=[,;:—–])\s+", sentence):
        if cur and len(cur) + len(piece) > limit:
            parts.append(cur)
            cur = piece
        else:
            cur = f"{cur} {piece}".strip()
    if cur:
        parts.append(cur)
    return parts


class OmniVoiceEngine(Engine):
    name = "omnivoice"
    normalize_numbers = True

    def __init__(self, voice: str, model: str = "k2-fsa/OmniVoice", steps: int = 32,
                 max_minutes: float = 150, cache: Path | None = None, ref_wav: str = "",
                 ref_text: str = "", seed: int = 7, pause: float = 0.35):
        super().__init__(voice)
        self.model_id, self.steps, self.max_minutes = model, steps, max_minutes
        # har bir ovoz tavsifi uchun alohida fayl: tavsifni o'zgartirsangiz, yangi ovoz yaratiladi
        cache_dir = Path(cache) if cache else Path.home() / ".cache" / "uzbooks"
        key = hashlib.sha1(f"{model}|{voice}|{seed}".encode()).hexdigest()[:10]
        self.cache = cache_dir / f"omnivoice_voice_{key}.pt"
        self.ref_wav, self.ref_text, self.seed, self.pause = ref_wav, ref_text, seed, pause
        self._prompt = None
        self._started = None

    def label(self):
        return f"omnivoice:{self.voice}" + (" (o'z namunangiz)" if self.ref_wav else "")

    def available(self):
        try:
            import numpy  # noqa: F401
            import omnivoice  # noqa: F401
            import torch  # noqa: F401
        except ImportError as e:
            return False, f"OmniVoice o'rnatilmagan ({e.name}); requirements-omnivoice.txt ni o'rnating"
        return True, ""

    # ---------- model ----------
    def _load(self):
        global _model
        if _model is None:
            import os
            import torch
            from omnivoice import OmniVoice
            torch.set_num_threads(max(1, os.cpu_count() or 1))
            t = time.time()
            print(f"  OmniVoice modeli yuklanmoqda ({self.model_id}, CPU)...")
            _model = OmniVoice.from_pretrained(self.model_id, device_map="cpu", dtype=torch.float32)
            print(f"  Model yuklandi: {time.time() - t:.0f} s")
        return _model

    def _gen_kwargs(self, model) -> dict:
        kw = {"num_step": self.steps}
        try:
            params = inspect.signature(model.generate).parameters
        except (TypeError, ValueError):
            params = {}
        for name in ("language", "language_id", "lang"):
            if name in params:
                kw[name] = "uz"
                break
        return kw

    def _generate(self, text: str, **extra):
        import numpy as np
        import torch
        model = self._load()
        torch.manual_seed(self.seed)
        out = model.generate(text=text, **self._gen_kwargs(model), **extra)
        audio = out[0] if isinstance(out, (list, tuple)) else out
        if hasattr(audio, "detach"):
            audio = audio.detach().cpu().numpy()
        audio = np.asarray(audio, dtype=np.float32).reshape(-1)
        if audio.size < SR * 0.2 or not np.isfinite(audio).all():
            raise TTSError("OmniVoice bo'sh yoki buzilgan audio qaytardi")
        return audio

    def _voice_prompt(self):
        if self._prompt is not None:
            return self._prompt
        model = self._load()
        from omnivoice import VoiceClonePrompt
        if self.ref_wav:
            print("  OmniVoice: sizning ovoz namunangizdan foydalanilmoqda")
            self._prompt = model.create_voice_clone_prompt(ref_audio=self.ref_wav,
                                                           ref_text=self.ref_text or None)
            return self._prompt
        if self.cache.exists():
            self._prompt = VoiceClonePrompt.load(str(self.cache))
            print(f"  OmniVoice: saqlangan ovoz ishlatildi ({self.cache.name})")
            return self._prompt
        # Birinchi marta: tavsif bo'yicha ovoz yaratib, namunasini saqlaymiz
        ref_text = ("Assalomu alaykum, aziz do'stlar. Bugun biz siz bilan juda foydali va qiziqarli "
                    "bir kitob haqida suhbatlashamiz.")
        audio = self._generate(ref_text, instruct=self.voice)
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        ref = self.cache.with_suffix(".wav")
        _write_wav(ref, audio)
        self._prompt = model.create_voice_clone_prompt(ref_audio=str(ref), ref_text=ref_text)
        self._prompt.save(str(self.cache))
        print(f"  OmniVoice: yangi ovoz yaratildi va saqlandi ({self.voice})")
        return self._prompt

    def _sentence(self, text: str):
        import numpy as np
        prompt = self._voice_prompt()
        parts = []
        for k, piece in enumerate(_split_long(text)):
            for attempt in range(2):
                self._check_budget()
                audio = self._generate(piece, voice_clone_prompt=prompt)
                cps = len(piece) / (audio.size / SR)
                if 3 <= cps <= 40:          # o'qish tezligi mantiqiy (gap tushib qolmagan / takrorlanmagan)
                    break
                print(f"  OmniVoice: g'alati tezlik ({cps:.1f} belgi/s), qayta urinish")
                self.seed += 1
            else:
                raise TTSError(f"OmniVoice gapni to'g'ri o'qiy olmadi: «{piece[:60]}...»")
            if k:
                parts.append(np.zeros(int(SR * 0.15), dtype=np.float32))
            parts.append(audio)
        return np.concatenate(parts)

    def _check_budget(self):
        if self._started and time.time() - self._started > self.max_minutes * 60:
            raise TTSError(f"OmniVoice {self.max_minutes:.0f} daqiqalik vaqt chegarasidan oshdi")

    def synth(self, spoken, original, stem):
        import numpy as np
        if self._started is None:
            self._started = time.time()
        gap = np.zeros(int(SR * self.pause), dtype=np.float32)
        audio, cues, t = [], [], 0.0
        t0 = time.time()
        for i, (sp, orig) in enumerate(zip(spoken, original)):
            a = self._sentence(sp)
            cues.append((t, t + a.size / SR, orig))
            audio += [a, gap]
            t += (a.size + gap.size) / SR
        out = stem.with_name(f"{stem.name}_omni.wav")
        _write_wav(out, np.concatenate(audio))
        print(f"  OmniVoice: {t:.0f} s ovoz {time.time() - t0:.0f} s da (RTF {(time.time() - t0) / max(t, 1):.2f})")
        return [out], cues


def _write_wav(path: Path, audio) -> None:
    import numpy as np
    peak = float(np.max(np.abs(audio))) or 1.0
    pcm = (audio / max(peak, 1.0) * 32767 * 0.98).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
