"""Pilot episode: the pre-written demo script, REAL Kaggle video + real Egyptian voices.
python scripts/run_pilot.py start | step"""
import os
import sys
from pathlib import Path

os.environ.setdefault("STUDIO_MODE", "demo")
os.environ.setdefault("VIDEO_PROVIDER", "kaggle")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio import orchestrator as orc  # noqa: E402
from studio.db import connect, kv_get, kv_set  # noqa: E402

with connect() as con:
    if sys.argv[1] == "start":
        idea = {"title": "سيد والمساعد الذكي", "premise": "زيزو بيشغّل مساعد ذكاء اصطناعي في القهوة والمعلم سيد بيعلّمه الفهلوة",
                "characters": ["sayed_fahlawa", "zizo_trend", "am_ragab", "om_abdo"]}
        eid = orc.start_episode(con, idea, None, "owner")
        kv_set(con, "pilot_episode", eid)
    eid = int(kv_get(con, "pilot_episode"))
    print("episode", eid, "→", orc.advance(con, eid, 20))
