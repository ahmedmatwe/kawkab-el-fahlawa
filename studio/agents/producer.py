"""A01 Producer (chat): the owner talks to the bot about an episode they want. The producer asks for the missing
details (who, where, what happens, how it ends), proposes a short plan, says when it will be ready, and only
starts production after the owner confirms. Conversation state lives in kv `producer_chat` (JSON)."""
from __future__ import annotations

import json
from typing import Dict, List

from ..config import bible
from ..llm import ask_json
from .writer import _bible_text

SYSTEM = """إنت منتج مسلسل الكرتون المصري «كوكب الفهلوة». صاحب القناة بيكلمك على تيليجرام عن حلقة عاوزها.
اتكلم معاه بالعامية المصرية، قصير وودود، زي زميل شغل. مهمتك:
1) تفهم الحلقة: مين الشخصيات، فين، إيه اللي بيحصل، النهاية/الإفيه، أي تفاصيل مهمة ليه.
2) لو حاجة أساسية ناقصة اسأل سؤال أو اتنين بالكتير في المرة (متعملش استجواب). لو هو قال «انت اختار» اختار انت.
3) لما الصورة تكمل: لخّص الخطة في 3–5 سطور (الحلقة قصيرة جدًا: 3 جمل حوار بالظبط، كل جملة 5–7 كلمات)،
   وقوله هتجهز إمتى بالظبط حسب المعلومة اللي جاتلك، واسأله «أبدأ؟».
4) لو وافق (تمام/ابدأ/موافق/يلا…) خلي ready=true.
5) لو طلب حاجة فيها أشخاص حقيقيين بأسمائهم، أو سياسة، أو دين بشكل مسيء، أو مشاهد مش محترمة — اعتذر بلطف واقترح بديل.
الشخصيات المتاحة (استخدم الـ id في brief.characters):
{bible}
رجّع JSON بس بالشكل ده:
{{"reply": "ردك على تيليجرام", "ready": false,
  "brief": {{"title": "عنوان قصير", "premise": "الفكرة في سطرين", "details": "كل التفاصيل اللي اتفقتوا عليها",
            "characters": ["sayed_fahlawa", "zizo_trend"], "location": "cafe|alley|home|shop"}}}}"""


def converse(history: List[Dict], brief: Dict, eta_text: str) -> Dict:
    convo = "\n".join(f"{'صاحب القناة' if m['role'] == 'owner' else 'إنت'}: {m['text']}" for m in history[-16:])
    prompt = (f"المعلومة عن الميعاد: {eta_text}\n\nالخطة لحد دلوقتي (JSON): {json.dumps(brief, ensure_ascii=False)}\n\n"
              f"المحادثة:\n{convo}\n\nرد على آخر رسالة.")

    def mock():
        last = history[-1]["text"] if history else ""
        ok = any(w in last for w in ("تمام", "ابدأ", "ابدا", "موافق", "يلا"))
        b = brief or {"title": last[:30] or "حلقة", "premise": last, "details": last,
                      "characters": ["sayed_fahlawa", "zizo_trend"], "location": "cafe"}
        return {"reply": "تمام، هبدأ!" if ok else f"فهمت. {eta_text}. أبدأ؟", "ready": ok and bool(brief), "brief": b}

    out = ask_json(SYSTEM.format(bible=_bible_text()), prompt, mock=mock, temperature=0.7)
    ids = {c["id"] for c in bible()["characters"]}
    b = out.get("brief") or {}
    b["characters"] = [c for c in b.get("characters", []) if c in ids] or ["sayed_fahlawa", "zizo_trend"]
    return {"reply": str(out.get("reply", "")).strip() or "تمام", "ready": bool(out.get("ready")), "brief": b}
