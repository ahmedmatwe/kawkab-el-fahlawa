"""A20 Cultural & Safety Reviewer: deterministic word list + an independent LLM review."""
from __future__ import annotations

import re
from typing import List, Tuple

from ..llm import ask_json

BANNED = ["حمار", "غبي", "متخلف", "يلعن", "زفت", "خول", "عرص", "شرموط", "وسخ", "كس", "طيز", "نيك", "بوس", "سكس",
          "خمرة", "بيرة", "حشيش", "مخدرات", "سيجارة", "رقص", "بكيني", "مايوه", "عيل", "طفل", "أطفال"]

SYSTEM = """You are the Cultural & Safety Reviewer for a family-friendly Egyptian cartoon. Review the script.
Flag: insults to groups (regions, Upper Egyptians, women, professions, religions, disabilities), bullying, innuendo,
real people named or mocked, unverified real events presented as fact, dangerous imitable acts, children on screen,
immodest clothing or scenes. Platform AI-content disclosure is always required (the series is AI-generated).
Return JSON: {"verdict":"pass|fix|block","issues":["Arabic"],"score":0-15}"""


def banned_hits(text: str) -> List[str]:
    return [w for w in BANNED if re.search(rf"(^|[\s،.!؟]){w}($|[\s،.!؟])", text)]


def review(script: dict) -> Tuple[str, List[str], int]:
    text = "\n".join(f"{l['speaker']}: {l['text']} [{l.get('action_en', '')}]" for l in script.get("lines", []))
    hits = banned_hits(text)
    data = ask_json(SYSTEM, f"Fact basis: {script.get('fact_basis') or 'fictional'}\n\n{text}",
                    mock=lambda: {"verdict": "pass", "issues": [], "score": 15}, temperature=0.1)
    verdict, issues, score = data.get("verdict", "fix"), list(data.get("issues", [])), int(data.get("score", 0))
    if hits:
        verdict, score = "block", 0
        issues.insert(0, "ألفاظ ممنوعة: " + "، ".join(hits))
    return verdict, issues, score
