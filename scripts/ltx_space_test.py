"""Try LTX-2 audio-to-video (lip sync from our own Egyptian voice) on a public Hugging Face Space via its
documented Gradio HTTP API. Usage: python scripts/ltx_space_test.py IMAGE AUDIO OUT.mp4 "prompt" [space-host]"""
import json
import sys
import requests

img, aud, out, prompt = sys.argv[1:5]
host = sys.argv[5] if len(sys.argv) > 5 else "https://multimodalart-ltx2-audio-to-video.hf.space"
api = f"{host}/gradio_api"
hdr = {}
import os
if os.environ.get("HF_TOKEN"):
    hdr["Authorization"] = f"Bearer {os.environ['HF_TOKEN']}"
files = [("files", open(img, "rb")), ("files", open(aud, "rb"))]
paths = requests.post(f"{api}/upload", files=files, headers=hdr, timeout=120).json()
fd = lambda p: {"path": p, "meta": {"_type": "gradio.FileData"}}
from subprocess import run
import imageio_ffmpeg, re
dur = re.search(r"Duration: (\d+):(\d+):([\d.]+)", run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", aud], capture_output=True, text=True).stderr)
secs = round(float(dur.group(3)) * 2) / 2
body = {"data": [fd(paths[0]), fd(paths[1]), prompt, "low quality, worst quality, deformed, distorted, extra people, text", max(1.0, secs), 7]}
eid = requests.post(f"{api}/call/generate", json=body, headers=hdr, timeout=60).json()["event_id"]
print("event", eid, "duration", secs, flush=True)
with requests.get(f"{api}/call/generate/{eid}", headers=hdr, stream=True, timeout=900) as r:
    ev = None
    for line in r.iter_lines(decode_unicode=True):
        if line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            data = line[5:].strip()
            if ev in ("complete", "error"):
                print(ev, data[:600], flush=True)
                if ev == "complete":
                    res = json.loads(data)[0]
                    url = res.get("video", res).get("url") if isinstance(res, dict) else None
                    if url:
                        open(out, "wb").write(requests.get(url, headers=hdr, timeout=300).content)
                        print("saved", out)
                break
