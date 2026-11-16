"""Lip-synced shots with Magic Hour AI Talking Photo (image + voice → talking clip), then the studio's own edit.
Usage: python scripts/magichour_talk.py EPISODE_DIR OUT.mp4 [only_idx]
EPISODE_DIR: frame_XX.jpg + line_XX.wav + script.json. Needs MAGICHOUR_API_KEY in .env. ~20 credits/s ('prompted')."""
import json, sys, time, wave
from pathlib import Path
import requests

d, out = Path(sys.argv[1]), Path(sys.argv[2])
only = int(sys.argv[3]) if len(sys.argv) > 3 else None
key = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("MAGICHOUR_API_KEY=")][-1]
H = {"Authorization": f"Bearer {key}"}
API = "https://api.magichour.ai/v1"


def upload(p: Path, kind: str) -> str:
    r = requests.post(f"{API}/files/upload-urls", headers=H, json={"items": [{"type": kind, "extension": p.suffix[1:]}]}, timeout=60)
    r.raise_for_status()
    it = r.json()["items"][0]
    requests.put(it["upload_url"], data=p.read_bytes(), timeout=300).raise_for_status()
    return it["file_path"]


script = json.loads((d / "script.json").read_text())
lines = script["lines"]
clips = []
for i, ln in enumerate(lines):
    f = f"{i:02d}"
    clip = d / f"shot_{f}.mp4"
    if (only is None or only == i) and not clip.exists():
        w = wave.open(str(d / f"line_{f}.wav")); secs = round(w.getnframes() / w.getframerate() + 0.2, 1)
        body = {"name": f"kawkab {script['title']} {f}", "start_seconds": 0, "end_seconds": secs, "resolution": "480p",  # free plan: 480p only
                "assets": {"image_file_path": upload(d / f"frame_{f}.jpg", "image"), "audio_file_path": upload(d / f"line_{f}.wav", "audio")},
                "style": {"generation_mode": "prompted",
                          "prompt": f"3D Pixar-style Egyptian cartoon scene, natural lip sync for the speaker only, everyone moves naturally: {ln.get('action_en', '')}"}}
        r = requests.post(f"{API}/ai-talking-photo", headers=H, json=body, timeout=60)
        if not r.ok:
            sys.exit(f"shot {i}: {r.status_code} {r.text[:400]}")
        pid = r.json()["id"]; print("shot", i, "project", pid, "credits", r.json().get("credits_charged"), flush=True)
        for _ in range(360):
            time.sleep(5)
            g = requests.get(f"{API}/video-projects/{pid}", headers=H, timeout=30)
            if not g.ok:
                continue
            p = g.json()
            st = p.get("status")
            if st == "complete":
                url = (p.get("downloads") or [{}])[0].get("url")
                clip.write_bytes(requests.get(url, timeout=300).content)
                print("shot", i, "done, credits", p.get("credits_charged"), flush=True)
                break
            if st in ("error", "canceled"):
                sys.exit(f"shot {i} {st}: {p.get('error')}")
        else:
            sys.exit(f"shot {i}: timed out")
    if clip.exists():
        clips.append(clip)

if only is None and len(clips) == len(lines):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from studio.edit import assemble
    final = assemble(d, script["title"], lines, clips, [d / f"line_{i:02d}.wav" for i in range(len(lines))], demo=False)
    out.write_bytes(Path(final).read_bytes()); print("saved", out)
