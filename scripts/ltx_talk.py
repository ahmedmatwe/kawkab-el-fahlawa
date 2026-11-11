"""Lip-synced image+audio-to-video on the LTX-2 Turbo Space. Usage: ltx_talk.py IMAGE AUDIO OUT.mp4 "prompt" [W H]"""
import json, os, sys, requests
img, aud, out, prompt = sys.argv[1:5]
W, H = (int(sys.argv[5]), int(sys.argv[6])) if len(sys.argv) > 6 else (576, 1024)
api = "https://alexnasa-ltx-2-turbo.hf.space/gradio_api"; hdr = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"}
up = lambda f: {"path": requests.post(f"{api}/upload", files=[("files", open(f, "rb"))], headers=hdr, timeout=120).json()[0], "meta": {"_type": "gradio.FileData"}}
data = [up(img), None, prompt, None, "Image-to-Video", False, 10, True, H, W, "No LoRA", up(aud)]
eid = requests.post(f"{api}/call/generate_video", json={"data": data}, headers=hdr, timeout=60).json()["event_id"]
with requests.get(f"{api}/call/generate_video/{eid}", headers=hdr, stream=True, timeout=1200) as r:
    ev = None
    for line in r.iter_lines(decode_unicode=True):
        if line.startswith("event:"): ev = line[6:].strip()
        elif line.startswith("data:") and ev in ("complete", "error"):
            d = line[5:].strip(); print(ev, d[:300])
            if ev == "complete":
                res = json.loads(d)[0]; v = res.get("video", res)
                open(out, "wb").write(requests.get(v["url"], headers=hdr, timeout=300).content); print("saved", out)
            break
