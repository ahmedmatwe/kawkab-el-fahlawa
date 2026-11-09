"""ffmpeg/ffprobe helpers. Uses system ffmpeg if present, else the static build from imageio-ffmpeg."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


def ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def run(args: List[str], timeout: int = 900) -> str:
    p = subprocess.run([ffmpeg(), "-hide_banner", "-y", *args], capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + p.stderr[-1500:])
    return p.stderr


def probe(path: Path) -> dict:
    """Stream info without ffprobe (not shipped by imageio-ffmpeg): parse `ffmpeg -i` output."""
    import re
    p = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    err = p.stderr
    info: dict = {"ok": "Invalid data" not in err and "No such file" not in err and "moov atom not found" not in err}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    info["duration"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0
    v = re.search(r"Stream #.*Video: (\w+).*?, (\d{2,5})x(\d{2,5})", err)
    if v:
        info.update(vcodec=v.group(1), width=int(v.group(2)), height=int(v.group(3)))
    fps = re.search(r"([\d.]+) fps", err)
    info["fps"] = float(fps.group(1)) if fps else 0.0
    info["has_audio"] = bool(re.search(r"Stream #.*Audio:", err))
    info["ok"] = info["ok"] and info["duration"] > 0
    return info


def duration(path: Path) -> float:
    return probe(path)["duration"]


def analyze(path: Path) -> dict:
    """Decode the whole file: catches corruption, black frames and loudness/silence."""
    import re
    p = subprocess.run([ffmpeg(), "-hide_banner", "-v", "info", "-i", str(path),
                        "-vf", "blackdetect=d=0.4:pix_th=0.08", "-af", "volumedetect,silencedetect=n=-45dB:d=1.5",
                        "-f", "null", "-"], capture_output=True, text=True, timeout=900)
    err = p.stderr
    blacks = [float(x) for x in re.findall(r"black_duration:([\d.]+)", err)]
    silences = [float(x) for x in re.findall(r"silence_duration: ([\d.]+)", err)]
    mean = re.search(r"mean_volume: (-?[\d.]+) dB", err)
    decode_errors = len(re.findall(r"(?i)(error while decoding|corrupt|invalid nal|concealing)", err))
    return {"returncode": p.returncode, "black_seconds": sum(blacks), "silence_seconds": sum(silences),
            "longest_silence": max(silences or [0.0]), "mean_volume_db": float(mean.group(1)) if mean else None,
            "decode_errors": decode_errors}


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def which_font_dir() -> Optional[str]:
    from .config import ROOT
    return str(ROOT / "assets/fonts")
