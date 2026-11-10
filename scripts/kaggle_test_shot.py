"""Render ONE real shot on Kaggle to measure time and quality before running full episodes.
Usage: python scripts/kaggle_test_shot.py submit | status | collect"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio.agents import consistency, storyboard, writer  # noqa: E402
from studio.video.kaggle import KaggleProvider  # noqa: E402

WD = Path(__file__).resolve().parents[1] / "data/kaggle_test"
WD.mkdir(parents=True, exist_ok=True)
prov = KaggleProvider()
cmd = sys.argv[1] if len(sys.argv) > 1 else "submit"

if cmd == "submit":
    script = writer.mock_script({"title": "test", "premise": "test"})
    shot = storyboard.build(script)[1]  # المعلم سيد: «اسمع مني أنا… أنا فاهم اللعبة دي!»
    shot["frame_path"] = str(consistency.first_frame(shot["ref"], WD / "frame.jpg", "cafe"))
    job = prov.submit(0, [shot], WD)
    (WD / "job.json").write_text(json.dumps({"job": job, "submitted": time.time(), "shot": shot}, ensure_ascii=False))
    print("submitted", job)
elif cmd == "status":
    j = json.loads((WD / "job.json").read_text())
    print(prov.poll(j["job"]), f"{(time.time() - j['submitted']) / 60:.1f} min")
elif cmd == "collect":
    j = json.loads((WD / "job.json").read_text())
    print(json.dumps(prov.collect(j["job"], WD), ensure_ascii=False, indent=1))
