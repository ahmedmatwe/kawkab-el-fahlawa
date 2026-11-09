"""A05 Head Writer + A06 Egyptian Dialogue (one creative call), A07 Script Editor (separate critical call
+ deterministic checks), A23 metadata. A weak script is rejected and rewritten with the editor's notes."""
from __future__ import annotations

from typing import List, Tuple

from ..config import bible, settings
from ..llm import ask_json
from .safety import banned_hits

CHARS_PER_SEC = 13.0  # measured pace of the Egyptian edge-tts voices incl. pauses

WRITER_SYSTEM = """You are the Head Comedy Writer AND Egyptian Dialogue Specialist of the 3D cartoon "كوكب الفهلوة".
Write ONE short vertical episode (35–55 seconds spoken) in natural Egyptian Arabic (عامية مصرية), family friendly.
Structure: hook in the first line (problem or absurd claim within 2 seconds) → a "clever" solution by a character →
escalation → comic disaster/twist ending → a closing reaction or catchphrase.
Each character keeps their personality and speech style. Use a catchphrase at most twice per episode.
Lines are short (max ~90 Arabic characters), each line is ONE speaker. 6–10 lines total.
No children on screen, no real people mocked, no profanity, no innuendo. Write Arabic with correct spelling.
Return JSON: {"title":"","logline":"","location":"cafe|alley|grocery|microbus|workshop",
"lines":[{"speaker":"character id","text":"Egyptian Arabic","emotion":"happy|angry|surprised|sad|laughing|thinking|neutral",
"action_en":"short English description of what the speaker physically does"}],
"metadata":{"title":"catchy honest Arabic title <=60 chars","description":"Arabic 1-2 sentences","hashtags":["#كوكب_الفهلوة", "... max 5"]}}"""

EDITOR_SYSTEM = """You are the strict Script Quality Editor of "كوكب الفهلوة". Score the script honestly; do not be generous.
Rubric (total 100): hook_first_2s 20, clarity 15, real comedic logic (not random jokes) 20, characters true to bible 15,
ending surprise 15, Egyptian dialogue naturalness 10, feasibility with simple 5-second animated shots 5.
Return JSON: {"score":0-100,"verdict":"approve|revise","problems":["Arabic"],"fixes":["Arabic concrete instructions"]}"""


def _bible_text() -> str:
    return "\n".join(
        f"- {c['id']} = {c['name']} ({c['age']}), {c['job']}. شخصيته: {c['personality']}. كلامه: {c['speech']}. "
        f"إفيهاته: {' / '.join(c['catchphrases'])}" for c in bible()["characters"])


def mock_script(idea: dict, weak: bool = False) -> dict:
    if weak:
        return {"title": idea["title"], "logline": "", "location": "cafe", "lines": [
            {"speaker": "sayed_fahlawa", "text": "أهلا", "emotion": "neutral", "action_en": "stands"}], "metadata": {}}
    return {
        "title": idea["title"], "logline": idea["premise"], "location": "cafe",
        "lines": [
            {"speaker": "zizo_trend", "text": "يا معلم! القهوة دي محتاجة مساعد ذكاء اصطناعي ياخد الطلبات!", "emotion": "happy", "action_en": "waves his smartphone excitedly"},
            {"speaker": "sayed_fahlawa", "text": "اسمع مني أنا… أنا فاهم اللعبة دي! شغّله وأنا أعلّمه الأصول.", "emotion": "laughing", "action_en": "pats his chest proudly"},
            {"speaker": "zizo_trend", "text": "خلاص اتعلم منك كل حاجة يا معلم… يا جدعان دي هتكسر الدنيا!", "emotion": "surprised", "action_en": "shows the phone screen"},
            {"speaker": "am_ragab", "text": "واحد شاي لو سمحت.", "emotion": "neutral", "action_en": "sits down on a wooden chair"},
            {"speaker": "zizo_trend", "text": "المساعد بيقول: الشاي بعشرة، والكرسي بخمسة، والقعدة في الضل بعشرين!", "emotion": "surprised", "action_en": "reads from the phone, shocked"},
            {"speaker": "am_ragab", "text": "أنا من أولها قلتلكم الموضوع مش طبيعي!", "emotion": "angry", "action_en": "throws his hands up angrily"},
            {"speaker": "sayed_fahlawa", "text": "الله! ده طلع شاطر… بس استنى، بيقول عليّا أنا كمان حساب قديم!", "emotion": "surprised", "action_en": "looks at the phone, eyes wide"},
            {"speaker": "om_abdo", "text": "أنا ماليش دعوة… بس المساعد ده بيقول إنك مدّيني تلات شهور شكك يا معلم!", "emotion": "laughing", "action_en": "points at Sayed with a teasing smile"},
            {"speaker": "sayed_fahlawa", "text": "اقفله يا زيزو! اقفله قبل ما يفتح دفاتر الحارة كلها!", "emotion": "angry", "action_en": "waves both hands in panic"},
        ],
        "metadata": {"title": "المعلم سيد علّم الذكاء الاصطناعي الفهلوة 😂", "description": "لما المساعد الذكي يتعلم فهلوة المعلم… ويطلع عليه هو! محتوى كرتوني مولّد بالذكاء الاصطناعي.",
                     "hashtags": ["#كوكب_الفهلوة", "#كرتون_مصري", "#كوميديا", "#ذكاء_اصطناعي"]},
    }


def estimate_seconds(script: dict) -> float:
    return sum(len(l.get("text", "")) / CHARS_PER_SEC + 0.35 for l in script.get("lines", []))


def deterministic_checks(script: dict) -> List[str]:
    """Hard rules that never depend on a model's opinion."""
    ids = {c["id"] for c in bible()["characters"]}
    lo, hi = settings()["target_seconds"]
    p: List[str] = []
    lines = script.get("lines") or []
    if not 4 <= len(lines) <= 12:
        p.append(f"عدد الجمل {len(lines)} (المطلوب 4–12)")
    for i, l in enumerate(lines):
        if l.get("speaker") not in ids:
            p.append(f"جملة {i + 1}: متكلم غير معروف {l.get('speaker')}")
        if not l.get("text") or len(l["text"]) > 120:
            p.append(f"جملة {i + 1}: فاضية أو أطول من 120 حرف")
    secs = estimate_seconds(script)
    if not lo - 5 <= secs <= hi:
        p.append(f"المدة المتوقعة {secs:.0f} ثانية (المطلوب {lo}–{hi})")
    hits = banned_hits(" ".join(l.get("text", "") for l in lines))
    if hits:
        p.append("ألفاظ ممنوعة: " + "، ".join(hits))
    return p


def write(idea: dict, notes: str = "", weak_mock: bool = False) -> dict:
    prompt = (f"Character bible:\n{_bible_text()}\n\nIdea:\nTitle: {idea['title']}\nPremise: {idea['premise']}\n"
              f"Characters to use: {', '.join(idea['characters'])}\nFact basis (only facts allowed): {idea.get('fact_basis') or 'none — fully fictional'}\n")
    if notes:
        prompt += f"\nThe editor rejected the previous draft. Fix ALL of these:\n{notes}\n"
    return ask_json(WRITER_SYSTEM, prompt, mock=lambda: mock_script(idea, weak=weak_mock))


def review(script: dict) -> Tuple[int, List[str], List[str]]:
    hard = deterministic_checks(script)
    lines = "\n".join(f"{l['speaker']}: {l['text']}  [{l.get('action_en', '')}]" for l in script.get("lines", []))
    mock_score = 40 if len(script.get("lines", [])) < 4 else 86
    data = ask_json(EDITOR_SYSTEM, f"Character bible:\n{_bible_text()}\n\nScript '{script.get('title')}':\n{lines}",
                    mock=lambda: {"score": mock_score, "verdict": "approve" if mock_score >= 75 else "revise",
                                  "problems": [] if mock_score >= 75 else ["السيناريو قصير جدًا ومفيهوش موقف"],
                                  "fixes": [] if mock_score >= 75 else ["اكتب موقف كامل بافتتاحية وتصعيد وقفلة"]},
                    temperature=0.2)
    score = int(data.get("score", 0))
    if hard:
        score = min(score, 60)  # a failed hard rule can never pass
    return score, hard + list(data.get("problems", [])), list(data.get("fixes", []))
