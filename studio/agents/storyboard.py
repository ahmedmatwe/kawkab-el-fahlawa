"""A08 Storyboard + A11 Prompt Engineer (deterministic, from the approved script and the Character Bible).
One shot per dialogue line: the speaker is on screen, framed from an approved reference image (image-to-video),
so identity comes from the reference picture, not from text alone."""
from __future__ import annotations

from typing import List

from ..config import bible, character, settings

CAMERA = ["medium close-up, eye level", "medium shot, slight low angle", "close-up on the face",
          "medium shot, slow push-in", "medium close-up, slight dutch angle for comedy", "close-up, quick zoom-in reaction"]

EMOTION_EN = {
    "happy": "smiling broadly, cheerful", "angry": "frowning angrily, waving hands", "surprised": "eyes wide open, eyebrows raised, shocked",
    "sad": "sad face, shoulders down", "laughing": "laughing heartily, head tilted back", "thinking": "thinking, hand on chin",
    "neutral": "relaxed natural expression",
}

NEGATIVE = ("different character, changed face, extra people, child, children, text, subtitles, watermark, logo, "
            "deformed hands, extra fingers, distorted face, blurry, low quality, flicker, realistic photo, live action, "
            "revealing clothes, nudity, static image, frozen, morphing")


def build(script: dict) -> List[dict]:
    b = bible()
    loc_key = script.get("location") if script.get("location") in b["locations"] else "alley"
    location = b["locations"][loc_key]
    shots = []
    for i, line in enumerate(script["lines"]):
        c = character(line["speaker"])
        emo = line.get("emotion", "neutral")
        prompt = (
            f"{b['series']['visual_style']}. Vertical 9:16 frame. {CAMERA[i % len(CAMERA)]}. "
            f"The same character as in the reference image: {c['look_en']}. Keep his/her exact face, mustache, outfit and colors. "
            f"Setting: {location}. Action: {line.get('action_en', 'talks')}, {EMOTION_EN.get(emo, EMOTION_EN['neutral'])}, "
            f"talking with natural lip movement and expressive hand gestures. Smooth natural motion, stable camera, cinematic lighting."
        )
        shots.append({
            "idx": i, "line": i, "speaker": c["id"], "text": line["text"], "emotion": emo,
            "camera": CAMERA[i % len(CAMERA)], "location": loc_key,
            "ref": c["refs"][i % len(c["refs"])],  # alternate approved references for variety
            "prompt": prompt, "negative": NEGATIVE,
        })
    return shots


def validate(shots: List[dict]) -> List[str]:
    g = settings()["generation"]
    errs = []
    ids = {c["id"] for c in bible()["characters"]}
    for s in shots:
        if s["speaker"] not in ids:
            errs.append(f"shot {s['idx']}: unknown character")
        if "9:16" not in s["prompt"]:
            errs.append(f"shot {s['idx']}: missing 9:16")
        if not s.get("ref"):
            errs.append(f"shot {s['idx']}: no reference image")
    if g["gen_width"] >= g["gen_height"]:
        errs.append("generation size is not portrait")
    return errs
