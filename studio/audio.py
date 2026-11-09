"""A13 Voice Director: fixed voice profile per character (config/characters.json → voice).
Engine: edge-tts with Microsoft's Egyptian neural voices (Shakir / Salma), free, no account.
Each character gets its own pitch/rate so the five voices stay distinguishable and stable across episodes."""
from __future__ import annotations

import asyncio
from pathlib import Path

from .config import character
from .media import run

EMOTION_RATE = {"angry": "+8%", "surprised": "+6%", "happy": "+4%", "laughing": "+4%", "sad": "-8%", "thinking": "-6%"}


def _add_pct(a: str, b: str) -> str:
    return f"{int(a.rstrip('%')) + int(b.rstrip('%')):+d}%"


async def _edge(text: str, voice: str, rate: str, pitch: str, out: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(out))


def synth_line(character_id: str, text: str, emotion: str, out_wav: Path, retries: int = 4) -> Path:
    v = character(character_id)["voice"]
    rate = _add_pct(v.get("rate", "+0%"), EMOTION_RATE.get(emotion, "+0%"))
    mp3 = out_wav.with_suffix(".mp3")
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    last = None
    for i in range(retries):
        try:
            asyncio.run(_edge(text, v["voice"], rate, v.get("pitch", "+0Hz"), mp3))
            if mp3.exists() and mp3.stat().st_size > 1000:
                break
        except Exception as e:  # transient network failure → exponential backoff
            last = e
        import time
        time.sleep(2 ** i)
    else:
        raise RuntimeError(f"TTS failed for {character_id}: {last}")
    # trim leading/trailing silence, mono 48k wav
    run(["-i", str(mp3), "-af",
         "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse,"
         "apad=pad_dur=0.12", "-ac", "1", "-ar", "48000", str(out_wav)])
    mp3.unlink(missing_ok=True)
    return out_wav
