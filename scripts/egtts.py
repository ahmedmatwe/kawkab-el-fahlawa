"""Egyptian-dialect speech from the CPU EGTTS Space. Usage: egtts.py "text" SPEAKER_REF.wav OUT.wav [temperature]"""
import json, os, sys, requests
text, ref, out = sys.argv[1:4]; temp = float(sys.argv[4]) if len(sys.argv) > 4 else 0.75
api = "https://mohamedrashad-egyptian-arabic-tts.hf.space/gradio_api"
hdr = {"Authorization": f"Bearer {os.environ['HF_TOKEN']}"} if os.environ.get("HF_TOKEN") else {}
p = requests.post(f"{api}/upload", files=[("files", open(ref, "rb"))], headers=hdr, timeout=120).json()[0]
eid = requests.post(f"{api}/call/infer_EGTTS", json={"data": [text, {"path": p, "meta": {"_type": "gradio.FileData"}}, temp]}, headers=hdr, timeout=60).json()["event_id"]
with requests.get(f"{api}/call/infer_EGTTS/{eid}", headers=hdr, stream=True, timeout=900) as r:
    ev = None
    for line in r.iter_lines(decode_unicode=True):
        if line.startswith("event:"): ev = line[6:].strip()
        elif line.startswith("data:") and ev in ("complete", "error"):
            d = line[5:].strip(); print(ev, d[:200])
            if ev == "complete":
                res = json.loads(d)[0]
                open(out, "wb").write(requests.get(res["url"], headers=hdr, timeout=300).content); print("saved", out)
            break
