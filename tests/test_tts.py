"""Ovoz tizimi testlari (internet va API kalitsiz ishlaydi; haqiqiy dvijoklar alohida — tts_test).

  python -m unittest discover -s tests -v
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("GEMINI_API_KEY", "test")

from src import audio_qa, compose, config, tts, tts_engines, uz_text  # noqa: E402
from src.tts_engines.base import Engine, TTSError, duration  # noqa: E402
from src.tts_engines.edge import EdgeEngine  # noqa: E402
from src.tts_engines.elevenlabs import cues_from_chars  # noqa: E402
from src.tts_engines.omnivoice import OmniVoiceEngine, _split_long  # noqa: E402

CPS = 14.0   # soxta dvijok: 14 belgi/soniya


def tone(path: Path, seconds: float, freq: int) -> Path:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"sine=frequency={freq}:sample_rate=24000:duration={seconds:.3f}",
                    "-af", "volume=0.3", str(path)], check=True)
    return path


class FakeEngine(Engine):
    """Har bir gapni ohang bilan "o'qiydi". mode: ok | unavailable | timeout | garbage | fail_at:N"""

    def __init__(self, name, freq, mode="ok"):
        super().__init__("fake")
        self.name, self.freq, self.mode, self.calls = name, freq, mode, 0

    def available(self):
        return (False, "o'rnatilmagan") if self.mode == "unavailable" else (True, "")

    def synth(self, spoken, original, stem):
        self.calls += 1
        if self.mode == "timeout":
            raise TTSError("180 s ichida javob kelmadi")
        if self.mode.startswith("fail_at:") and self.calls > int(self.mode.split(":")[1]):
            raise TTSError("server 503")
        if self.mode == "garbage":
            p = stem.with_name(stem.name + "_bad.mp3")
            p.write_bytes(b"not audio" * 500)
            return [p], [(0, 1, s) for s in original]
        pieces, cues, t = [], [], 0.0
        for k, s in enumerate(spoken):
            d = max(0.4, len(s) / CPS)
            pieces.append(tone(stem.with_name(f"{stem.name}_{k}.wav"), d, self.freq))
            cues.append((t, t + d, original[k]))
            t += d
        return pieces, cues


UZ = ("O'zbekiston go'zal yurt. Gʻalaba va oʻqish — sh, ch, ng tovushlari! "
      "Napoleon Xill 1937-yilda kitob yozdi. Sotuvlar 25% ga oshdi?")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        tts_engines._engines.clear()
        tts_engines.warnings.clear()
        self.p = mock.patch.multiple(config, TTS_PROVIDER="edge", TTS_FALLBACK="omnivoice",
                                     TTS_NORMALIZE="auto")
        self.p.start()

    def tearDown(self):
        self.p.stop()
        tts_engines._engines.clear()

    def use(self, primary, fallback):
        tts_engines._engines.update({"edge": primary, "omnivoice": fallback})


class TestUzText(unittest.TestCase):
    def test_numbers(self):
        f = uz_text.for_speech
        self.assertEqual(f("1937-yilda"), "bir ming to'qqiz yuz o'ttiz yettinchi yilda")
        self.assertEqual(f("25%"), "yigirma besh foiz")
        self.assertEqual(f("2,5 mln"), "ikki butun besh million")
        self.assertEqual(f("10:30"), "o'n o'ttiz")
        self.assertEqual(f("50-yil"), "elliginchi yil")
        self.assertEqual(f("1 000 000"), "bir million")
        self.assertEqual(f("100"), "yuz")

    def test_apostrophes(self):
        self.assertEqual(uz_text.for_speech("Oʻzbek gʻoya ma’no", full=False), "O'zbek g'oya ma'no")
        # apostrof almashtirish uzunlikni o'zgartirmaydi (ElevenLabs vaqtlari uchun muhim)
        s = "Oʻzbek gʻoya ma’no"
        self.assertEqual(len(uz_text.for_speech(s, full=False)), len(s))


class TestManager(Base):
    def test_short_text(self):
        a, b = FakeEngine("edge", 440), FakeEngine("omnivoice", 660)
        self.use(a, b)
        [(d, cues)] = tts.synthesize_sections([UZ], [self.tmp / "a.mp3"])
        self.assertEqual(len(cues), 4)
        self.assertTrue(all(c[0] < c[1] <= d for c in cues))
        self.assertEqual([c[0] for c in cues], sorted(c[0] for c in cues))
        self.assertIn("Gʻalaba", cues[1][2])                # subtitrda asl matn qoladi
        self.assertEqual(b.calls, 0)
        self.assertEqual(tts.voice_label(), "edge:fake")
        errors, _, info = audio_qa.check(self.tmp / "a.mp3", len(UZ))
        self.assertEqual(errors, [])
        self.assertAlmostEqual(info["duration"], d, delta=0.1)

    def test_long_text_and_10_minutes(self):
        a = FakeEngine("edge", 440)
        self.use(a, FakeEngine("omnivoice", 660))
        para = ("Bu juda uzun gap bo'lib, unda kitobning asosiy g'oyasi, muallifning tajribasi va "
                "o'quvchi uchun amaliy maslahatlar batafsil tushuntiriladi. ")
        texts = [para * 9 for _ in range(7)]                # 7 bo'lim, ~8000 belgi ≈ 10 daqiqa
        out = tts.synthesize_sections(texts, [self.tmp / f"s{i}.mp3" for i in range(7)])
        total = sum(d for d, _ in out)
        self.assertGreater(total, 8 * 60)
        self.assertLess(total, 12 * 60)
        for d, cues in out:
            self.assertEqual(len(cues), 9)
            self.assertLessEqual(cues[-1][1], d)
            self.assertGreaterEqual(d - cues[-1][1], tts_engines.END_PAD - 0.15)   # oxirgi pauza

    def test_unavailable_falls_back(self):
        a, b = FakeEngine("edge", 440, "unavailable"), FakeEngine("omnivoice", 660)
        self.use(a, b)
        tts.synthesize_sections([UZ], [self.tmp / "a.mp3"])
        self.assertEqual(tts.voice_label(), "omnivoice:fake")
        self.assertTrue(any("zaxira" in w for w in tts.warnings()))

    def test_timeout_falls_back(self):
        a, b = FakeEngine("edge", 440, "timeout"), FakeEngine("omnivoice", 660)
        self.use(a, b)
        tts.synthesize_sections([UZ], [self.tmp / "a.mp3"])
        self.assertEqual(b.calls, 1)
        self.assertIn("javob kelmadi", " ".join(tts.warnings()))

    def test_failure_midway_redoes_all_sections(self):
        a, b = FakeEngine("edge", 440, "fail_at:2"), FakeEngine("omnivoice", 660)
        self.use(a, b)
        out = tts.synthesize_sections([UZ, UZ, UZ], [self.tmp / f"s{i}.mp3" for i in range(3)])
        self.assertEqual(len(out), 3)
        self.assertEqual(b.calls, 3)                         # hammasi zaxira bilan qaytadan
        self.assertEqual(tts.voice_label(), "omnivoice:fake")

    def test_invalid_audio_falls_back(self):
        a, b = FakeEngine("edge", 440, "garbage"), FakeEngine("omnivoice", 660)
        self.use(a, b)
        tts.synthesize_sections([UZ], [self.tmp / "a.mp3"])
        self.assertEqual(tts.voice_label(), "omnivoice:fake")

    def test_all_fail(self):
        self.use(FakeEngine("edge", 440, "timeout"), FakeEngine("omnivoice", 660, "unavailable"))
        with self.assertRaises(TTSError) as cm:
            tts.synthesize_sections([UZ], [self.tmp / "a.mp3"])
        self.assertIn("edge", str(cm.exception))
        self.assertIn("omnivoice", str(cm.exception))

    def test_invalid_provider_name(self):
        self.use(FakeEngine("edge", 440), FakeEngine("omnivoice", 660))
        with mock.patch.object(config, "TTS_PROVIDER", "edgee"):
            self.assertEqual(tts.provider(), "edge")
        self.assertTrue(any("noto'g'ri" in w for w in tts_engines.warnings))

    def test_auto_keeps_old_behaviour(self):
        with mock.patch.object(config, "TTS_PROVIDER", "auto"), \
                mock.patch.object(config, "ELEVENLABS_API_KEY", lambda: ""):
            self.assertEqual(tts.provider(), "edge")
        with mock.patch.object(config, "TTS_PROVIDER", "auto"), \
                mock.patch.object(config, "ELEVENLABS_API_KEY", lambda: "k"), \
                mock.patch.object(config, "ELEVENLABS_VOICE_ID", lambda: "v"):
            self.assertEqual(tts.provider(), "elevenlabs")

    def test_number_normalization_only_for_engines_that_need_it(self):
        seen = {}

        class Spy(FakeEngine):
            def synth(self, spoken, original, stem):
                seen[self.name] = spoken
                return super().synth(spoken, original, stem)

        self.use(Spy("edge", 440), Spy("omnivoice", 660))
        tts.synthesize_sections(["1937-yil."], [self.tmp / "a.mp3"])
        self.assertEqual(seen["edge"], ["1937-yil."])               # Edge: avvalgidek
        b = Spy("omnivoice", 660)
        b.normalize_numbers = True
        tts_engines._engines["edge"] = b
        tts.synthesize_sections(["1937-yil."], [self.tmp / "b.mp3"])
        self.assertIn("yettinchi", seen["omnivoice"][0])

    def test_secrets_redacted(self):
        with mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": "sk_secret_123456"}):
            self.assertNotIn("sk_secret_123456", tts_engines._redact("xato sk_secret_123456 bor"))

    def test_subtitles_render_with_ffmpeg(self):
        self.use(FakeEngine("edge", 440), FakeEngine("omnivoice", 660))
        [(d, cues)] = tts.synthesize_sections([UZ], [self.tmp / "a.mp3"])
        ass = compose.write_ass(cues, self.tmp / "s.ass")
        out = self.tmp / "v.mp4"
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            f"color=c=black:s=640x360:d={d:.2f}", "-i", str(self.tmp / "a.mp3"),
                            "-vf", f"ass={ass}", "-shortest", "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-300:])
        self.assertAlmostEqual(duration(out), d, delta=0.3)


class TestEngineHelpers(unittest.TestCase):
    def test_edge_sentence_boundaries(self):
        ev = [("SentenceBoundary", 0.1, 1.5, "a"), ("SentenceBoundary", 1.7, 3.0, "b")]
        cues = EdgeEngine._cues(["A.", "B."], ev, 3.2)
        self.assertEqual(cues, [(0.1, 1.5, "A."), (1.7, 3.0, "B.")])

    def test_edge_falls_back_to_proportional(self):
        cues = EdgeEngine._cues(["Aaaa.", "Bb."], [], 4.0)
        self.assertAlmostEqual(cues[1][1], 4.0)

    def test_elevenlabs_char_alignment(self):
        text = "Salom. Dunyo!"
        starts = [i * 0.1 for i in range(len(text))]
        ends = [s + 0.1 for s in starts]
        cues = cues_from_chars(text, ["Salom.", "Dunyo!"], ["Salom.", "Dunyo!"], starts, ends, 1.3)
        self.assertAlmostEqual(cues[1][0], 0.7)
        self.assertAlmostEqual(cues[1][1], 1.3)

    def test_omnivoice_long_sentence_split(self):
        s = ", ".join(["bu uzun gapning bir qismi"] * 30) + "."
        parts = _split_long(s)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 300 for p in parts))
        self.assertEqual(" ".join(parts), s)

    def test_omnivoice_reports_missing_install(self):
        ok, why = OmniVoiceEngine("male").available()
        try:
            import omnivoice  # noqa: F401
        except ImportError:
            self.assertFalse(ok)
            self.assertIn("requirements-omnivoice", why)


class TestRealEdge(unittest.TestCase):
    """Haqiqiy Edge TTS (internet kerak). Ishlamasa — SKIPPED (NOT TESTED)."""

    def test_real_edge(self):
        eng = EdgeEngine("uz-UZ-SardorNeural", timeout=30, attempts=1)
        ok, why = eng.available()
        if not ok:
            self.skipTest(f"NOT TESTED: {why}")
        tmp = Path(tempfile.mkdtemp())
        try:
            d, cues = tts_engines.section(eng, UZ, tmp / "edge.mp3")
        except TTSError as e:
            self.skipTest(f"NOT TESTED (tarmoq): {str(e)[:100]}")
        self.assertEqual(len(cues), 4)
        self.assertGreater(d, 3)


if __name__ == "__main__":
    unittest.main()


class TestOmniVoiceCodePath(unittest.TestCase):
    """OmniVoice kodini SOXTA model bilan tekshiradi (haqiqiy model bu yerda yo'q).
    Haqiqiy o'zbekcha sifat — faqat tts_test orqali tinglab baholanadi."""

    def setUp(self):
        import sys
        import types

        import numpy as np
        self.created = []
        test = self

        class Prompt:
            def save(self, path):
                Path(path).write_text("voice")
                test.created.append(path)

            @staticmethod
            def load(path):
                return Prompt()

        class Model:
            def generate(self, text, num_step=32, language=None, instruct=None, voice_clone_prompt=None):
                test.lang = language
                n = int(24000 * max(0.5, len(text) / 14))
                return [np.sin(np.arange(n) / 10).astype(np.float32) * 0.3]

            def create_voice_clone_prompt(self, ref_audio, ref_text=None):
                assert Path(ref_audio).exists()
                return Prompt()

        ov = types.ModuleType("omnivoice")
        ov.OmniVoice = types.SimpleNamespace(from_pretrained=lambda *a, **k: Model())
        ov.VoiceClonePrompt = Prompt
        torch = types.ModuleType("torch")
        torch.float32, torch.manual_seed, torch.set_num_threads = "f32", lambda s: None, lambda n: None
        self.mods = mock.patch.dict(sys.modules, {"omnivoice": ov, "torch": torch})
        self.mods.start()
        import src.tts_engines.omnivoice as om
        om._model = None
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        self.mods.stop()
        import src.tts_engines.omnivoice as om
        om._model = None

    def test_section_with_fake_model(self):
        eng = OmniVoiceEngine("male, low pitch", cache=self.tmp)
        self.assertEqual(eng.available(), (True, ""))
        d, cues = tts_engines.section(eng, UZ, self.tmp / "o.mp3")
        self.assertEqual(len(cues), 4)
        self.assertEqual(self.lang, "uz")                    # til parametri uzatiladi
        self.assertEqual(len(self.created), 1)               # ovoz bir marta yaratilib saqlandi
        self.assertTrue(all(b <= d for _, b, _ in cues))
        # ikkinchi marta — saqlangan ovoz ishlatiladi, yangisi yaratilmaydi
        eng2 = OmniVoiceEngine("male, low pitch", cache=self.tmp)
        tts_engines.section(eng2, "Ikkinchi sinov gapi.", self.tmp / "o2.mp3")
        self.assertEqual(len(self.created), 1)
        # boshqa tavsif — boshqa ovoz fayli
        self.assertNotEqual(eng.cache, OmniVoiceEngine("female", cache=self.tmp).cache)

    def test_time_budget(self):
        eng = OmniVoiceEngine("male", cache=self.tmp, max_minutes=0.0001)
        eng._started = 1.0
        with self.assertRaises(TTSError):
            eng.synth(["Salom."], ["Salom."], self.tmp / "x")


class TestAisha(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.wav = tone(self.tmp / "src.wav", 1.2, 300).read_bytes()
        self.sent = []

    def _post(self, codes):
        test = self

        def post(url, data, timeout, headers):
            test.sent.append(data)
            code = codes.pop(0) if codes else 201
            r = mock.Mock(status_code=code, text="err")
            r.json = lambda: {"audio_path": "/media/tts_audios/x.wav"}
            return r
        return post

    def _get(self, url, timeout):
        return mock.Mock(status_code=200, content=self.wav)

    def make(self, **kw):
        from src.tts_engines.aisha import AishaEngine
        return AishaEngine("key", **kw)

    def test_section(self):
        eng = self.make()
        with mock.patch("src.tts_engines.aisha.requests.post", self._post([])), \
                mock.patch("src.tts_engines.aisha.requests.get", self._get), \
                mock.patch("src.tts_engines.aisha.time.sleep"):
            d, cues = tts_engines.section(eng, UZ, self.tmp / "a.mp3")
        self.assertEqual(len(cues), 4)
        self.assertEqual(len(self.sent), 4)                       # har bir gap — bitta so'rov
        self.assertEqual(self.sent[0]["model"], "Gulnoza")
        self.assertIn("yettinchi", self.sent[2]["transcript"])   # sonlar so'z bilan
        self.assertTrue(all(b <= d for _, b, _ in cues))
        self.assertGreater(cues[1][0], cues[0][1])                # gaplar orasida pauza

    def test_retry_then_ok(self):
        eng = self.make()
        with mock.patch("src.tts_engines.aisha.requests.post", self._post([503, 503])), \
                mock.patch("src.tts_engines.aisha.requests.get", self._get), \
                mock.patch("src.tts_engines.aisha.time.sleep"):
            tts_engines.section(eng, "Salom dunyo.", self.tmp / "b.mp3")
        self.assertEqual(len(self.sent), 3)

    def test_no_balance_is_clear_error(self):
        eng = self.make()
        with mock.patch("src.tts_engines.aisha.requests.post", self._post([402])), \
                mock.patch("src.tts_engines.aisha.time.sleep"):
            with self.assertRaises(TTSError) as cm:
                tts_engines.section(eng, "Salom dunyo.", self.tmp / "c.mp3")
        self.assertIn("balans", str(cm.exception))
        self.assertEqual(len(self.sent), 1)                       # balans yo'q — qayta urinmaydi

    def test_custom_voice_and_long_sentence(self):
        from src.tts_engines.aisha import split_long
        eng = self.make(voice_id="42")
        long = " ".join(["so'z"] * 400) + "."
        self.assertTrue(all(len(p) <= 950 for p in split_long(long)))
        with mock.patch("src.tts_engines.aisha.requests.post", self._post([])), \
                mock.patch("src.tts_engines.aisha.requests.get", self._get), \
                mock.patch("src.tts_engines.aisha.time.sleep"):
            eng.synth([long], [long], self.tmp / "d")
        self.assertGreater(len(self.sent), 1)
        self.assertEqual(self.sent[0]["voice_id"], "42")
        self.assertNotIn("mood", self.sent[0])

    def test_without_key_uses_public_mode(self):
        from src.tts_engines.aisha import AishaEngine
        eng = AishaEngine("")
        self.assertEqual(eng.available(), (True, ""))
        self.assertTrue(eng.public)
        ok, why = AishaEngine("", voice_id="5").available()
        self.assertFalse(ok)
        self.assertIn("AISHA_API_KEY", why)

    def test_rejected_key_switches_to_public(self):
        eng = self.make()
        heads = []
        test = self

        def post(url, data, timeout, headers):
            heads.append(dict(headers))
            r = mock.Mock(status_code=403 if "X-Api-Key" in headers else 201, text="no")
            r.json = lambda: {"audio_path": "/m/x.wav"}
            return r
        with mock.patch("src.tts_engines.aisha.requests.post", post), \
                mock.patch("src.tts_engines.aisha.requests.get", self._get), \
                mock.patch("src.tts_engines.aisha.time.sleep"):
            d, cues = tts_engines.section(eng, UZ, self.tmp / "p.mp3")
        self.assertTrue(eng.public)
        self.assertIn("X-Api-Key", heads[0])
        self.assertTrue(all("X-Api-Key" not in h for h in heads[1:]))
        self.assertEqual(len(cues), 4)


class TestPronunciation(unittest.TestCase):
    def test_lexicon_and_suffixes(self):
        f = uz_text.for_speech
        self.assertEqual(f("Henry Ford va Napoleon Hill."), "Genri Ford va Napoleon Xill.")
        self.assertEqual(f("25% ga oshdi"), "yigirma besh foizga oshdi")
        self.assertEqual(f("10:30 da"), "o'n o'ttizda")

    def test_okina_style(self):
        self.assertEqual(uz_text.for_speech("O'zbek g'oya ma'no", apostrophe="ʻ"), "Oʻzbek gʻoya maʼno")

    def test_default_normalizes_for_all_engines(self):
        with mock.patch.object(config, "TTS_NORMALIZE", "on"):
            self.assertTrue(tts_engines._normalize_numbers(EdgeEngine()))

    def test_edge_word_cues_use_spoken_text(self):
        ev = [("WordBoundary", i * 0.5, i * 0.5 + 0.4, "w") for i in range(8)]
        cues = EdgeEngine._cues(["1937-yil.", "Bu yaxshi."], ev, 4.0,
                                ["bir ming to'qqiz yuz o'ttiz yettinchi yil.", "Bu yaxshi."])
        self.assertAlmostEqual(cues[1][0], 3.5)   # 7 so'zdan keyin
        self.assertEqual(cues[0][2], "1937-yil.")
