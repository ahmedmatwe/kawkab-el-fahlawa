"""Lip-synced shots with WaveSpeed InfiniteTalk (image + voice → talking clip), then the studio's own edit.
Usage: python scripts/wavespeed_talk.py EPISODE_DIR OUT.mp4 [480p|720p]
EPISODE_DIR holds frame_XX.jpg + line_XX.wav + script.json (from the state branch). Needs WAVESPEED_API_KEY in .env."""
import json, os, sys, time
from pathlib import Path
import requests

d, out = Path(sys.argv[1]), Path(sys.argv[2])
res = sys.argv[3] if len(sys.argv) > 3 else "720p"
key = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("WAVESPEED_API_KEY=")][0]
H = {"Authorization": f"Bearer {key}"}
API = "https://api.wavespeed.ai/api/v3"


def upload(p: Path) -> str:
    r = requests.post(f"{API}/media/upload/binary", headers=H, files={"file": (p.name, p.read_bytes())}, timeout=120)
    r.raise_for_status()
    return r.json()["data"]["download_url"]


script = json.loads((d / "script.json").read_text())
lines = script["lines"]
clips = []
for i, ln in enumerate(lines):
    f = f"{i:02d}"
    clip = d / f"shot_{f}.mp4"
    if not clip.exists():
        body = {"image": upload(d / f"frame_{f}.jpg"), "audio": upload(d / f"line_{f}.wav"), "resolution": res, "seed": 7,
                "prompt": f"3D Pixar-style Egyptian cartoon character talking naturally with expressive face and small gestures: {ln.get('action_en', '')}"}
        r = requests.post(f"{API}/wavespeed-ai/infinitetalk", headers={**H, "Content-Type": "application/json"}, json=body, timeout=60)
        r.raise_for_status()
        tid = r.json()["data"]["id"]
        print("shot", i, "task", tid, flush=True)
        for _ in range(240):
            time.sleep(5)
            try:
                g = requests.get(f"{API}/predictions/{tid}/result", headers=H, timeout=30)
                if g.status_code in (429,) or g.status_code >= 500:
                    continue
                data = g.json()["data"]
            except Exception:
                continue
            if data["status"] == "completed":
                clip.write_bytes(requests.get(data["outputs"][0], timeout=300).content)
                print("shot", i, "done", data.get("timings"), flush=True)
                break
            if data["status"] in ("failed", "cancelled", "timeout", "deleted"):
                sys.exit(f"shot {i} {data['status']}: {data.get('error')}")
        else:
            sys.exit(f"shot {i}: timed out")
    clips.append(clip)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from studio.edit import assemble
final = assemble(d, script["title"], lines, clips, [d / f"line_{i:02d}.wav" for i in range(len(lines))], demo=False)
out.write_bytes(Path(final).read_bytes())
print("saved", out)
