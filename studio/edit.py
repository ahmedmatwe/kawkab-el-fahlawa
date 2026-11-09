"""A16 Video Editor + A17 Subtitles + A14 Audio Engineer.
Every shot is cut to the length of its dialogue line (slowed ≤1.35× or held on the last frame if the line is
longer than the 5-second clip), upscaled to 1080x1920, joined, captioned in Arabic (ASS, safe area) and
loudness-normalised to -14 LUFS. An SRT copy is written next to the video."""
from __future__ import annotations

from pathlib import Path
from typing import List

from PIL import Image, ImageFilter

from .config import ROOT, bible, character, settings
from .media import duration, run, which_font_dir

COLORS = {"sayed_fahlawa": "&H0000C8FF", "zizo_trend": "&H0000FFFF", "om_abdo": "&H00FF80D0",
          "abdo_ekhtera": "&H00FFC060", "am_ragab": "&H006090FF"}  # ASS = &HAABBGGRR
INTRO_SECS = 1.6


def _ts(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _srt_ts(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def intro_card(out: Path, title: str) -> Path:
    W, H = settings()["video"]["width"], settings()["video"]["height"]
    poster = Image.open(ROOT / "assets/characters/source/poster_b.png").convert("RGB")
    bg = poster.resize((round(poster.width * H / poster.height), H)).filter(ImageFilter.GaussianBlur(18))
    left = (bg.width - W) // 2
    bg = bg.crop((left, 0, left + W, H))
    logo = poster.crop((470, 0, 1050, 320))
    logo = logo.resize((W - 80, round(logo.height * (W - 80) / logo.width)), Image.LANCZOS)
    bg.paste(logo, (40, 520))
    png = out.with_suffix(".png")
    bg.save(png)
    run(["-loop", "1", "-i", str(png), "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", str(INTRO_SECS),
         "-vf", f"scale={W}:{H},fps={settings()['video']['fps']},format=yuv420p,fade=t=out:st={INTRO_SECS - 0.3}:d=0.3",
         "-c:v", "libx264", "-c:a", "pcm_s16le", "-shortest", str(out)])
    return out


def segment(clip: Path, wav: Path, out: Path) -> float:
    """Fit one generated clip to its dialogue line. Returns the segment length."""
    v = settings()["video"]
    W, H, fps = v["width"], v["height"], v["fps"]
    d_audio = duration(wav)
    target = max(d_audio + 0.25, 1.8)
    c = duration(clip)
    speed = min(max(target / c, 1.0), 1.35)
    hold = max(0.0, target - c * speed)
    vf = (f"setpts={speed:.4f}*PTS,tpad=stop_mode=clone:stop_duration={hold + 0.1:.2f},"
          f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},"
          f"unsharp=5:5:0.6,fps={fps},format=yuv420p")
    run(["-i", str(clip), "-i", str(wav), "-filter_complex",
         f"[0:v]{vf}[v];[1:a]apad,atrim=0:{target:.3f}[a]", "-map", "[v]", "-map", "[a]",
         "-t", f"{target:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "pcm_s16le", str(out)])
    return target


RLM = "\u200f"


def wrap_rtl(text: str, width: int = 24) -> str:
    """Break long Arabic lines into ≤2-3 balanced rows and pin punctuation to the right-to-left order."""
    words, rows, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            rows.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        rows.append(cur)
    return "\\N".join(RLM + r + RLM for r in rows)


def write_subs(lines: List[dict], starts: List[float], lens: List[float], ass: Path, srt: Path, demo: bool) -> None:
    v = settings()["video"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {v['width']}
PlayResY: {v['height']}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Line,Cairo,82,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,6,2,2,70,70,420,178
Style: Name,Cairo,56,&H0000C8FF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,0,0,1,5,1,2,70,70,640,178
Style: Demo,Cairo,44,&H000000FF,&H00FFFFFF,&H00FFFFFF,&H00000000,1,0,0,0,100,100,0,0,1,3,0,8,40,40,160,178

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev, srt_rows = [], []
    for i, (l, st, ln) in enumerate(zip(lines, starts, lens)):
        en = st + ln - 0.05
        name = character(l["speaker"])["name"]
        body = wrap_rtl(l["text"])
        name_margin = 420 + 100 * (body.count("\\N") + 1) + 10  # sit just above the caption block
        ev.append(f"Dialogue: 0,{_ts(st)},{_ts(en)},Name,,0,0,{name_margin},,{{\\c{COLORS.get(l['speaker'], '&H00FFFFFF')}}}{name}")
        ev.append(f"Dialogue: 1,{_ts(st)},{_ts(en)},Line,,0,0,0,,{{\\fad(80,60)}}{body}")
        srt_rows.append(f"{i + 1}\n{_srt_ts(st)} --> {_srt_ts(en)}\n{name}: {l['text']}\n")
    if demo:
        total = starts[-1] + lens[-1] if starts else 1
        ev.append(f"Dialogue: 2,{_ts(0)},{_ts(total)},Demo,,0,0,0,,نسخة تجريبية DEMO — مش للنشر")
    ass.write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    srt.write_text("\n".join(srt_rows), encoding="utf-8")


def assemble(workdir: Path, title: str, lines: List[dict], clips: List[Path], wavs: List[Path], demo: bool) -> Path:
    segs, lens = [], []
    intro = intro_card(workdir / "seg_intro.mp4", title)
    for i, (clip, wav) in enumerate(zip(clips, wavs)):
        seg = workdir / f"seg_{i:02d}.mp4"
        lens.append(segment(clip, wav, seg))
        segs.append(seg)
    starts, t = [], INTRO_SECS
    for ln in lens:
        starts.append(t)
        t += ln
    lst = workdir / "concat.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in [intro] + segs))
    joined = workdir / "joined.mp4"
    run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c:v", "libx264", "-crf", "18", "-c:a", "pcm_s16le", str(joined)])
    ass, srt = workdir / "captions.ass", workdir / "captions.srt"
    write_subs(lines, starts, lens, ass, srt, demo)
    final = workdir / "final.mp4"
    _burn(joined, ass, final)
    return final


def _burn(joined: Path, ass: Path, final: Path) -> None:
    import os
    cwd = os.getcwd()
    os.chdir(ass.parent)  # libass filter paths are simplest when relative
    try:
        run(["-i", joined.name, "-vf", f"ass={ass.name}:fontsdir={which_font_dir()}",
             "-af", "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000", "-c:v", "libx264", "-preset", "medium",
             "-crf", "20", "-profile:v", "high", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
             "-movflags", "+faststart", final.name], timeout=1800)
    finally:
        os.chdir(cwd)
