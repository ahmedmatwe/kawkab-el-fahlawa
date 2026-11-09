"""A09 Character Consistency: builds every shot's first frame from an APPROVED reference (never from a
newly generated picture) and checks generated clips against that reference.
Check = colour-histogram similarity of the clip's middle frame vs. the reference (cheap, deterministic).
It catches big identity/outfit drift; subtle face changes still need the human preview in Telegram."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from ..config import ROOT, settings
from ..media import ffmpeg


def first_frame(ref: str, out: Path) -> Path:
    g = settings()["generation"]
    W, H = g["gen_width"], g["gen_height"]
    im = Image.open(ROOT / ref).convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - W) // 2, max(0, int((im.height - H) * 0.15))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.crop((left, top, left + W, top + H)).save(out, quality=90)
    return out


def _hist(im: Image.Image):
    im = im.convert("RGB").resize((96, 160))
    h = im.histogram()
    s = float(sum(h)) or 1.0
    return [x / s for x in h]


def similarity(ref_frame: Path, clip: Path) -> float:
    tmp = clip.with_suffix(".mid.jpg")
    subprocess.run([ffmpeg(), "-hide_banner", "-y", "-ss", "2.5", "-i", str(clip), "-frames:v", "1", str(tmp)],
                   capture_output=True)
    if not tmp.exists():
        return 0.0
    a, b = _hist(Image.open(ref_frame)), _hist(Image.open(tmp))
    tmp.unlink(missing_ok=True)
    return sum(min(x, y) for x, y in zip(a, b))  # histogram intersection, 1.0 = identical colours


THRESHOLD = 0.55
