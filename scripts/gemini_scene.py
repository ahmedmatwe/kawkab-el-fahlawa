"""One 9:16 scene frame with several characters together in a location, from their approved reference images (Gemini image).
Usage: gemini_scene.py OUT.png "scene description" ref1.png ref2.png [...] [--model M]"""
import base64, json, os, sys, requests
args = [a for a in sys.argv[1:]]
model = "gemini-3.1-flash-image"
if "--model" in args:
    i = args.index("--model"); model = args[i + 1]; del args[i:i + 2]
out, desc, refs = args[0], args[1], args[2:]
key = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("GEMINI_API_KEY=")][-1]
parts = [{"inline_data": {"mime_type": "image/png", "data": base64.b64encode(open(r, "rb").read()).decode()}} for r in refs]
parts.append({"text": desc})
body = {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "9:16"}}}
r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  headers={"x-goog-api-key": key}, json=body, timeout=300)
d = r.json()
if "error" in d:
    sys.exit(f"{model}: {d['error'].get('code')} {d['error'].get('message','')[:300]}")
for p in d["candidates"][0]["content"]["parts"]:
    if "inlineData" in p or "inline_data" in p:
        x = p.get("inlineData") or p.get("inline_data")
        open(out, "wb").write(base64.b64decode(x["data"])); print("saved", out, model); break
else:
    sys.exit("no image: " + json.dumps(d)[:300])
