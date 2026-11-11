"""Egyptian-dialect TTS locally (NAMAA-Egyptian-TTS on Chatterbox, MIT). Usage: egy_tts.py OUT_DIR"""
import sys, torch, torchaudio as ta
from huggingface_hub import hf_hub_download
from safetensors.torch import load_file
from chatterbox import mtl_tts
out = sys.argv[1]
dev = "mps" if torch.backends.mps.is_available() else "cpu"
_load = torch.load
torch.load = lambda *a, **k: _load(*a, **{**k, "map_location": torch.device(dev)})
m = mtl_tts.ChatterboxMultilingualTTS.from_pretrained(device=dev)
m.t3.load_state_dict(load_file(hf_hub_download("NAMAA-Space/NAMAA-Egyptian-TTS", "t3_mtl23ls_v2.safetensors"), device=dev))
m.t3.to(dev).eval()
lines = {"zizo": ("يا معلم سيد! أنا جبتلك اختراع يعرف كل حاجة في الدنيا!", "data/trial/zizo.wav", 0.8),
         "sayed": ("حتى اللي في دماغي؟!", "data/trial/sayed.wav", 0.6)}
for who, (text, ref, ex) in lines.items():
    for tag, prompt in (("ref", ref), ("default", None)):
        torch.manual_seed(7)
        w = m.generate(text, language_id="ar", audio_prompt_path=prompt, exaggeration=ex, cfg_weight=0.4)
        ta.save(f"{out}/eg_{who}_{tag}.wav", w.cpu(), m.sr); print("saved", who, tag, flush=True)
