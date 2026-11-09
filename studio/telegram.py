"""Telegram Bot API (official HTTPS API). Only messages from TELEGRAM_CHAT_ID are accepted;
everything else is ignored. Message text is treated as a command choice, never as code."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import requests

from .config import env, redact


def enabled() -> bool:
    return bool(env("TELEGRAM_BOT_TOKEN") and env("TELEGRAM_CHAT_ID"))


def _api(method: str, files=None, timeout: int = 60, **params):
    url = f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/{method}"
    for attempt in range(3):
        try:
            if files:
                r = requests.post(url, data=params, files=files, timeout=300)
            else:
                r = requests.post(url, json=params, timeout=timeout)
            data = r.json()
            if data.get("ok"):
                return data["result"]
            if r.status_code == 429:
                import time
                time.sleep(int(data.get("parameters", {}).get("retry_after", 5)))
                continue
            raise RuntimeError(redact(f"telegram {method}: {data.get('description')}"))
        except requests.RequestException as e:
            if attempt == 2:
                raise RuntimeError(redact(f"telegram {method}: {e}"))
    return None


def _kb(buttons: Optional[List[List[tuple]]]):
    if not buttons:
        return None
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in buttons]}


def send(text: str, buttons=None) -> Optional[int]:
    if not enabled():
        print("[telegram off]", text[:200])
        return None
    params = {"chat_id": env("TELEGRAM_CHAT_ID"), "text": text[:4000]}
    kb = _kb(buttons)
    if kb:
        params["reply_markup"] = kb
    res = _api("sendMessage", **params)
    return res.get("message_id") if res else None


def send_video(path: Path, caption: str, buttons=None) -> Optional[int]:
    if not enabled():
        print("[telegram off] video", path)
        return None
    params = {"chat_id": env("TELEGRAM_CHAT_ID"), "caption": caption[:1000], "supports_streaming": "true"}
    kb = _kb(buttons)
    if kb:
        params["reply_markup"] = json.dumps(kb)
    with open(path, "rb") as f:
        res = _api("sendVideo", files={"video": (path.name, f, "video/mp4")}, **params)
    return res.get("message_id") if res else None


def updates(offset: int) -> List[dict]:
    if not enabled():
        return []
    res = _api("getUpdates", offset=offset, timeout=0, allowed_updates=["message", "callback_query"]) or []
    chat = str(env("TELEGRAM_CHAT_ID"))
    out = []
    for u in res:
        msg = u.get("message") or (u.get("callback_query") or {}).get("message") or {}
        u["_trusted"] = str(msg.get("chat", {}).get("id")) == chat
        out.append(u)
    return out


def answer_callback(cb_id: str, text: str = "") -> None:
    if enabled():
        try:
            _api("answerCallbackQuery", callback_query_id=cb_id, text=text[:180])
        except Exception:
            pass
