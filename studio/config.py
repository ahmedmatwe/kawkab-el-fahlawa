from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("STUDIO_DATA", ROOT / "data"))


def settings() -> dict:
    return json.loads((ROOT / "config/settings.json").read_text(encoding="utf-8"))


def bible() -> dict:
    return json.loads((ROOT / "config/characters.json").read_text(encoding="utf-8"))


def character(cid: str) -> dict:
    for c in bible()["characters"]:
        if c["id"] == cid:
            return c
    raise KeyError(f"unknown character {cid}")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def demo_mode() -> bool:
    """Demo mode = mock LLM/video providers; everything it produces is labelled DEMO."""
    return env("STUDIO_MODE", "demo") != "production"


SECRET_NAMES = ("GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN", "KAGGLE_KEY", "KAGGLE_API_TOKEN")


def redact(text: str) -> str:
    """Strip any configured secret value from text before it is logged or sent anywhere."""
    out = str(text)
    for n in SECRET_NAMES:
        v = os.environ.get(n, "")
        if len(v) >= 6:
            out = out.replace(v, "***")
    return out
