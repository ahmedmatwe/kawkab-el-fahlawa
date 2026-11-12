"""Egyptian-colloquial voices with Gemini TTS (gemini-3.1-flash-tts-preview; the owner picked it by ear).
Each character has a fixed prebuilt voice + a spoken-style brief in config/characters.json → voice.gemini.
One request per line so every shot gets its own WAV. Raises QuotaExceeded on 429 so callers can fall back."""
from __future__ import annotations

import base64, os, time, wave
from pathlib import Path

import requests

from .config import character

MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.1-flash-tts-preview")
URL = "https://generativelanguage.googleapis.com/v1beta/models/{}:generateContent"
EMOTION_AR = {"angry": "بعصبية", "surprised": "باندهاش", "happy": "بفرحة", "laughing": "وهو بيضحك",
              "sad": "بحزن", "thinking": "بتفكير وشك", "excited": "بحماس شديد"}


class QuotaExceeded(RuntimeError):
    pass


def _retry_delay(r):
    try:
        for x in r.json()["error"].get("details", []):
            if "retryDelay" in x:
                return float(x["retryDelay"].rstrip("s"))
    except Exception:
        pass
    return None


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY")) and os.environ.get("STUDIO_MODE") != "demo" and os.environ.get("GEMINI_TTS", "1") != "0"


def synth(character_id: str, text: str, emotion: str, out_wav: Path, retries: int = 3) -> Path:
    g = character(character_id)["voice"]["gemini"]
    how = EMOTION_AR.get(emotion, "")
    prompt = (f"اقرأ الجملة دي بالعامية المصرية الطبيعية، نطق قاهري زي ممثلين الكرتون المصري، مش فصحى. "
              f"المتكلم: {g['style']}. قولها {how}:\n{text}")
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": g["voice"]}}}}}
    for i in range(retries + 3):
        r = requests.post(URL.format(MODEL), headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]}, json=body, timeout=180)
        if r.status_code == 429:
            wait = _retry_delay(r)
            if wait is None or wait > 120 or "PerDay" in r.text:  # daily free quota is used up → let caller fall back
                raise QuotaExceeded(r.text[:300])
            time.sleep(wait + 2)  # per-minute limit → wait and retry
            continue
        if r.ok:
            try:
                pcm = base64.b64decode(r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
                break
            except (KeyError, IndexError):
                pass
        time.sleep(2 ** i)
    else:
        raise RuntimeError(f"Gemini TTS failed: {r.status_code} {r.text[:300]}")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
    return out_wav
