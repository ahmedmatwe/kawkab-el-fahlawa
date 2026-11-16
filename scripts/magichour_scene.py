"""One vertical scene frame with several characters together, from approved references (Magic Hour AI Image Editor,
free model flux-2-klein, 640px, ~5 credits). Usage: magichour_scene.py OUT.png "description" ref1 ref2 [...]"""
import sys, time
from pathlib import Path
import requests
out, desc, refs = sys.argv[1], sys.argv[2], sys.argv[3:]
key = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("MAGICHOUR_API_KEY=")][-1]
H = {"Authorization": f"Bearer {key}"}; API = "https://api.magichour.ai/v1"
def upload(p):
    p = Path(p); r = requests.post(f"{API}/files/upload-urls", headers=H, json={"items": [{"type": "image", "extension": p.suffix[1:]}]}, timeout=60)
    r.raise_for_status(); it = r.json()["items"][0]
    requests.put(it["upload_url"], data=p.read_bytes(), timeout=300).raise_for_status(); return it["file_path"]
body = {"name": "kawkab scene", "image_count": 1, "model": "flux-2-klein", "aspect_ratio": "9:16", "resolution": "640px",
        "style": {"prompt": desc}, "assets": {"image_file_paths": [upload(r) for r in refs]}}
r = requests.post(f"{API}/ai-image-editor", headers=H, json=body, timeout=60)
if not r.ok: sys.exit(f"{r.status_code} {r.text[:300]}")
pid = r.json()["id"]; print("project", pid, "credits", r.json().get("credits_charged"), flush=True)
for _ in range(120):
    time.sleep(3); p = requests.get(f"{API}/image-projects/{pid}", headers=H, timeout=30).json()
    if p.get("status") == "complete":
        open(out, "wb").write(requests.get(p["downloads"][0]["url"], timeout=120).content); print("saved", out); break
    if p.get("status") in ("error", "canceled"): sys.exit(f"{p.get('status')}: {p.get('error')}")
