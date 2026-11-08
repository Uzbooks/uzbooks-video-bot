"""Ovoz sifatini avtomatik tekshirish (FFmpeg orqali, qo'shimcha kutubxonasiz).

errors   — jiddiy: fayl buzilgan, bo'sh, gaplar tushib qolgan yoki ortiqcha takror (dvijok almashtiriladi)
warnings — ogohlantirish: uzun jimlik, juda baland/past ovoz
"""
import re
import subprocess
from pathlib import Path

MIN_CPS, MAX_CPS = 5.0, 32.0      # o'zbekcha nutq odatda 11-18 belgi/soniya
LONG_SILENCE = 2.5                # soniya


def _ffmpeg_stats(path: Path, filters: str) -> str:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", filters,
                        "-f", "null", "-"], capture_output=True, text=True, timeout=600)
    return r.stderr


def probe_duration(path: Path) -> float | None:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True, timeout=60)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def check(path: Path, text_chars: int) -> tuple[list[str], list[str], dict]:
    errors, warnings, info = [], [], {}
    if not path.exists() or path.stat().st_size < 1000:
        return [f"{path.name}: audio fayl yo'q yoki bo'sh"], [], info
    dur = probe_duration(path)
    if not dur or dur < 0.5:
        return [f"{path.name}: audio fayl buzilgan yoki juda qisqa"], [], info
    info["duration"] = round(dur, 2)
    cps = text_chars / dur
    info["chars_per_sec"] = round(cps, 1)
    if text_chars > 40 and cps > MAX_CPS:
        errors.append(f"{path.name}: matnga nisbatan ovoz juda qisqa ({cps:.0f} belgi/s) — gaplar tushib qolgan bo'lishi mumkin")
    if text_chars > 40 and cps < MIN_CPS:
        errors.append(f"{path.name}: matnga nisbatan ovoz juda uzun ({cps:.1f} belgi/s) — takror yoki jimlik")

    log = _ffmpeg_stats(path, f"silencedetect=noise=-45dB:d={LONG_SILENCE},volumedetect")
    sil = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", log)]
    starts = [float(x) for x in re.findall(r"silence_start: (-?[\d.]+)", log)]
    inner = [d for s, d in zip(starts, sil) if s > 0.3 and s + d < dur - 0.3]
    if inner:
        warnings.append(f"{path.name}: {len(inner)} ta uzun jimlik (eng uzuni {max(inner):.1f} s)")
    if sum(sil) > dur * 0.5:
        errors.append(f"{path.name}: audioning yarmidan ko'pi jimlik")
    m = re.search(r"max_volume: (-?[\d.]+) dB", log)
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", log)
    if m:
        info["max_db"] = float(m[1])
        if float(m[1]) >= -0.1:
            warnings.append(f"{path.name}: ovoz cho'qqisi 0 dB ga yetgan (clipping xavfi)")
    if mean:
        info["mean_db"] = float(mean[1])
        if float(mean[1]) < -35:
            warnings.append(f"{path.name}: ovoz juda past ({mean[1]} dB)")
    return errors, warnings, info
