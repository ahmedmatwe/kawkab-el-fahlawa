"""Two-speaker Egyptian-colloquial dialogue with Gemini TTS. Usage: gemini_tts.py OUT.wav [model]"""
import base64, json, os, sys, wave, requests
out = sys.argv[1]; model = sys.argv[2] if len(sys.argv) > 2 else "gemini-3.8-flash-tts"
key = [l.split("=", 1)[1].strip() for l in open(".env") if l.startswith("GEMINI_API_KEY=")][0]
prompt = """اقرأ الحوار ده بالعامية المصرية الطبيعية، نطق قاهري زي ممثلين الكرتون المصري، مش فصحى:
زيزو (شاب متحمس جدًا، داخل القهوة بيجري ومبسوط): يا معلّم سيّد! أنا جبتلك اختراع يعرف كل حاجة في الدنيا!
سيد (راجل كبير، صوته تخين، بيرفع حاجبه بشك وسخرية): حتى اللي في دماغي؟!"""
lines = [("زيزو", "يا معلّم سيّد! أنا جبتلك اختراع يعرف كل حاجة في الدنيا!"), ("سيد", "حتى اللي في دماغي؟!")]
style = "اتكلموا بالعامية المصرية الطبيعية، نطق قاهري زي ممثلين الكرتون المصري، مش فصحى. زيزو شاب متحمس جدًا داخل القهوة بيجري. سيد راجل كبير صوته تخين بيرفع حاجبه بشك وسخرية."
parts = [{"text": t, "speechMetadata": {"speaker": sp}} for sp, t in lines] if "3.8" in model else [{"text": prompt}]
body = {"contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": "زيزو", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}},
            {"speaker": "سيد", "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Algenib"}}}]}}}}
r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                  headers={"x-goog-api-key": key}, json=body, timeout=300)
d = r.json()
if "error" in d: raise SystemExit(json.dumps(d["error"], ensure_ascii=False)[:500])
pcm = base64.b64decode(d["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])
with wave.open(out, "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
print("saved", out, round(len(pcm) / 48000, 2), "s", model)
