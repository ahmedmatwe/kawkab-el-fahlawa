"""Render one image-to-video shot on a public Hugging Face Space through its documented Gradio HTTP API.
Usage: python scripts/space_shot.py {ltx|wan} IMAGE OUT.mp4 "prompt" SECONDS"""
import json, os, sys, requests
kind, img, out, prompt, secs = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], float(sys.argv[5])
host = {"ltx": "https://lightricks-ltx-2-3.hf.space",
        "wan": "https://zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space"}[kind]
api, hdr = f"{host}/gradio_api", ({"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {})
path = requests.post(f"{api}/upload", files=[("files", open(img, "rb"))], headers=hdr, timeout=120).json()[0]
fd = {"path": path, "meta": {"_type": "gradio.FileData"}}
if kind == "ltx":
    data = [fd, prompt, secs, False, 10, True, int(os.environ.get("H", 864)), int(os.environ.get("W", 1536))]
else:
    neg = "low quality, worst quality, blurry, deformed face, extra fingers, bad hands, static, subtitles, text artifacts"
    data = [fd, prompt, 6, neg, secs, 1, 1, 42, True]
eid = requests.post(f"{api}/call/generate_video", json={"data": data}, headers=hdr, timeout=60).json()["event_id"]
print(kind, "event", eid, flush=True)
with requests.get(f"{api}/call/generate_video/{eid}", headers=hdr, stream=True, timeout=1200) as r:
    ev = None
    for line in r.iter_lines(decode_unicode=True):
        if line.startswith("event:"): ev = line[6:].strip()
        elif line.startswith("data:") and ev in ("complete", "error"):
            data = line[5:].strip(); print(ev, data[:800], flush=True)
            if ev == "complete":
                res = json.loads(data)[0]
                v = res.get("video", res) if isinstance(res, dict) else res
                url = v.get("url") if isinstance(v, dict) else None
                if url:
                    open(out, "wb").write(requests.get(url, headers=hdr, timeout=300).content); print("saved", out)
            break
