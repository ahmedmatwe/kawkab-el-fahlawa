"""Edit one image with the official Qwen-Image-Edit Space. Usage: space_edit.py IN.png OUT.png "prompt" [seed]"""
import json, os, sys, requests
src, out, prompt = sys.argv[1:4]; seed = int(sys.argv[4]) if len(sys.argv) > 4 else 0
api = "https://qwen-qwen-image-edit.hf.space/gradio_api"; hdr = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"}
p = requests.post(f"{api}/upload", files=[("files", open(src, "rb"))], headers=hdr, timeout=120).json()[0]
data = [{"path": p, "meta": {"_type": "gradio.FileData"}}, prompt, seed, seed == 0, 4.0, 40, False]
eid = requests.post(f"{api}/call/infer", json={"data": data}, headers=hdr, timeout=60).json()["event_id"]
with requests.get(f"{api}/call/infer/{eid}", headers=hdr, stream=True, timeout=900) as r:
    ev = None
    for line in r.iter_lines(decode_unicode=True):
        if line.startswith("event:"): ev = line[6:].strip()
        elif line.startswith("data:") and ev in ("complete", "error"):
            d = line[5:].strip(); print(ev, d[:400])
            if ev == "complete":
                res = json.loads(d)[0]; res = res[0] if isinstance(res, list) else res
                res = res.get("image", res) if isinstance(res, dict) else res
                open(out, "wb").write(requests.get(res["url"], headers=hdr, timeout=300).content); print("saved", out)
            break
