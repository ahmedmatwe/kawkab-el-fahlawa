"""A18 Visual QA, A19 Audio QA (deterministic ffmpeg measurements) and A21 Final Quality Controller.
Missing data is never treated as a pass."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from ..config import settings
from ..media import analyze, probe


def check_clip(path: Path, expect_portrait: bool = True) -> List[str]:
    """Used on every generated shot before editing: corrupt / wrong size / too short → regenerate."""
    if not path.exists() or path.stat().st_size < 2000:
        return ["الملف ناقص أو تالف"]
    info = probe(path)
    if not info["ok"]:
        return ["الملف تالف ومش بيتقري"]
    errs = []
    if expect_portrait and info.get("width", 1) >= info.get("height", 0):
        errs.append(f"المقاس غلط {info.get('width')}x{info.get('height')} (لازم رأسي)")
    if info["duration"] < 2.0:
        errs.append(f"اللقطة قصيرة جدًا {info['duration']:.1f}s")
    return errs


def visual_audio_qa(final: Path) -> Tuple[int, int, int, List[str]]:
    """Returns (animation/image score /20, audio score /15, edit+caption score /10, problems)."""
    s = settings()
    lo, hi = s["target_seconds"]
    W, H = s["video"]["width"], s["video"]["height"]
    problems: List[str] = []
    info = probe(final)
    if not info["ok"]:
        return 0, 0, 0, ["الفيديو النهائي تالف"]
    vis, aud, edit = 20, 15, 10
    if (info.get("width"), info.get("height")) != (W, H):
        problems.append(f"المقاس {info.get('width')}x{info.get('height')} مش {W}x{H}"); vis = 0
    if not lo - 3 <= info["duration"] <= hi + 8:
        problems.append(f"المدة {info['duration']:.0f}s خارج المطلوب {lo}–{hi}"); edit -= 5
    a = analyze(final)
    if a["decode_errors"]:
        problems.append(f"أخطاء فك ترميز: {a['decode_errors']}"); vis -= 10
    if a["black_seconds"] > 0.5:
        problems.append(f"شاشة سودا {a['black_seconds']:.1f}s"); vis -= 8
    if not info["has_audio"] or a["mean_volume_db"] is None:
        problems.append("مفيش صوت"); aud = 0
    else:
        if a["mean_volume_db"] < -30:
            problems.append(f"الصوت واطي جدًا ({a['mean_volume_db']} dB)"); aud -= 6
        if a["longest_silence"] > 2.5:
            problems.append(f"سكوت طويل {a['longest_silence']:.1f}s"); aud -= 5
    aud -= 3  # no automatic lip-sync verification yet → never full marks
    return max(vis, 0), max(aud, 0), max(edit, 0), problems


def final_decision(script_score: int, consistency_scores: List[float], vqa: Tuple[int, int, int, List[str]],
                   safety: Tuple[str, List[str], int], demo: bool) -> Tuple[str, int, dict]:
    vis, aud, edit, problems = vqa
    verdict, issues, safety_score = safety
    cons = (sum(consistency_scores) / len(consistency_scores)) if consistency_scores else 0.0
    breakdown = {
        "script": round(script_score * 20 / 100), "consistency": round(min(cons / 0.85, 1.0) * 20),
        "animation": vis, "audio": aud, "edit": edit, "safety": safety_score,
    }
    total = sum(breakdown.values())
    breakdown["problems"] = problems + issues
    if verdict == "block":
        return "REJECTED", total, breakdown
    if demo:
        return "HUMAN_REVIEW_REQUIRED", total, breakdown  # demo output is never publishable
    if verdict == "fix" or breakdown["consistency"] < 12 or breakdown["animation"] < 10:
        return "REVISION_REQUIRED", total, breakdown
    if total >= settings()["quality"]["pass_score"]:
        return "APPROVED", total, breakdown
    return "HUMAN_REVIEW_REQUIRED", total, breakdown
