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


# Location backdrops cut from the approved posters (no new AI imagery). Blurred like a shallow depth of field
# so the sharp approved character stays the subject.
BACKDROPS = {
    "cafe": ("assets/characters/source/poster_b.png", (1150, 0, 1536, 180)),
    "alley": ("assets/characters/source/poster_b.png", (0, 0, 460, 190)),
}


def _cover(im: Image.Image, W: int, H: int, top_bias: float = 0.15) -> Image.Image:
    scale = max(W / im.width, H / im.height)
    im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    left, top = (im.width - W) // 2, max(0, int((im.height - H) * top_bias))
    return im.crop((left, top, left + W, top + H))


def backdrop(location: str, W: int, H: int) -> Image.Image:
    from PIL import ImageEnhance, ImageFilter
    src, box = BACKDROPS.get(location, BACKDROPS["alley"])
    bg = _cover(Image.open(ROOT / src).convert("RGB").crop(box), W, H, 0.0)
    bg = bg.filter(ImageFilter.GaussianBlur(5))
    return ImageEnhance.Brightness(bg).enhance(0.92)


def first_frame(ref: str, out: Path, location: str = "alley") -> Path:
    """Approved reference → first frame. Cut-outs (*_cutout.png, transparent) are placed in the episode's
    location; scene references are framed as they are. The character itself is never redrawn."""
    g = settings()["generation"]
    W, H = g["gen_width"], g["gen_height"]
    im = Image.open(ROOT / ref)
    if im.mode == "RGBA" and "_cutout" in ref:
        im = im.crop(im.getbbox())
        full_body = im.height / im.width > 1.25 and "_full" in ref
        target_h = int(H * (0.86 if full_body else 0.80))
        scale = min(target_h / im.height, W * 0.98 / im.width)
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
        frame = backdrop(location, W, H)
        frame.paste(im, ((W - im.width) // 2, H - im.height - (int(H * 0.04) if full_body else 0)), im)
    else:
        frame = _cover(im.convert("RGB"), W, H)
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.save(out, quality=92)
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
