# Kawkab El Fahlawa — shot renderer that runs on a free Kaggle GPU.
# Generated per episode by studio/video/kaggle.py: the JOB below (prompts + base64 first frames) is filled in.
# Model: Wan 2.2 TI2V-5B (Apache-2.0, open weights) through Hugging Face diffusers, image-to-video.
import base64, io, json, os, subprocess, sys, time, traceback

JOB = json.loads(base64.b64decode("__JOB_B64__").decode("utf-8"))
OUT = "/kaggle/working"
os.environ.setdefault("HF_HOME", "/tmp/hf")
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
log = open(f"{OUT}/render_log.txt", "a")


def say(*a):
    msg = time.strftime("%H:%M:%S ") + " ".join(str(x) for x in a)
    print(msg, flush=True)
    log.write(msg + "\n"); log.flush()


say("job", JOB["episode_id"], "shots", len(JOB["shots"]))
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers>=0.35", "transformers", "accelerate",
                "ftfy", "imageio", "imageio-ffmpeg", "sentencepiece"], check=False)

import torch  # noqa: E402
from PIL import Image  # noqa: E402
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline  # noqa: E402
from diffusers.utils import export_to_video  # noqa: E402

say("gpus", torch.cuda.device_count(), [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())])
if torch.cuda.device_count() == 0:
    # Fail fast and say why (unverified phone / GPU quota used up) instead of a confusing model-load error.
    with open(f"{OUT}/status.json", "w") as f:
        json.dump({"episode_id": JOB["episode_id"], "fatal": "no GPU (phone not verified or weekly GPU quota used)",
                   "shots": {f"shot_{s['idx']:02d}": {"ok": False, "error": "no GPU"} for s in JOB["shots"]}}, f)
    say("FATAL no GPU")
    sys.exit(0)
# T4 has no native bf16: bf16 falls back to the "math" attention kernel which needs ~6 GB per call (OOM).
# fp16 enables the memory-efficient attention kernel on T4.
major, _ = torch.cuda.get_device_capability(0)
dtype = torch.bfloat16 if major >= 8 else torch.float16
torch.backends.cuda.enable_mem_efficient_sdp(True)
vae = AutoencoderKLWan.from_pretrained(JOB["model"], subfolder="vae", torch_dtype=torch.float32)
pipe = WanImageToVideoPipeline.from_pretrained(JOB["model"], vae=vae, torch_dtype=dtype)
if major >= 8:
    pipe.enable_model_cpu_offload()
else:
    # Measured on Kaggle T4 (2026-11-10): whole-model offload OOMs (15.4 GB); layer-by-layer works,
    # 384x672x81 frames in ~13 min per shot.
    pipe.enable_sequential_cpu_offload()
    pipe._seq_offload = True
try:
    pipe.vae.enable_tiling()
except Exception:
    pass
say("model loaded", dtype)

status = {}
for shot in JOB["shots"]:
    name = f"shot_{shot['idx']:02d}"
    if os.path.exists(f"{OUT}/{name}.mp4"):
        continue
    t0 = time.time()
    try:
        img = Image.open(io.BytesIO(base64.b64decode(shot["frame_b64"]))).convert("RGB")
        img = img.resize((JOB["width"], JOB["height"]))
        frames = None
        # full size first; on OOM fall back to a smaller size so the shot still renders
        for (w, h, n) in [(JOB["width"], JOB["height"], JOB["frames"]), (384, 672, JOB["frames"]), (384, 672, 49)]:
            try:
                frames = pipe(image=img.resize((w, h)), prompt=shot["prompt"], negative_prompt=shot["negative"],
                              height=h, width=w, num_frames=n, num_inference_steps=JOB["steps"], guidance_scale=5.0,
                              generator=torch.Generator("cpu").manual_seed(1000 + shot["idx"])).frames[0]
                say(name, "rendered", w, h, n)
                break
            except torch.OutOfMemoryError:
                tb = traceback.format_exc()
                say(name, "OOM at", w, h, n, "| where:", " <- ".join(
                    l.strip() for l in tb.splitlines() if l.strip().startswith("File") and "site-packages" in l)[-900:],
                    "| mem GB:", [round(torch.cuda.memory_allocated(i) / 1e9, 1) for i in range(torch.cuda.device_count())])
                torch.cuda.empty_cache()
                if not getattr(pipe, "_seq_offload", False):
                    # strongest memory saver: stream weights layer by layer (slower, but fits 15 GB)
                    pipe.remove_all_hooks()
                    pipe.enable_sequential_cpu_offload()
                    pipe._seq_offload = True
                    say("switched to sequential cpu offload")
        if frames is None:
            raise RuntimeError("out of GPU memory at every size")
        import numpy as np
        arr = np.asarray(frames[len(frames) // 2], dtype="float32")
        if not np.isfinite(arr).all() or arr.mean() < 0.02:
            raise RuntimeError(f"bad frames (mean {float(np.nan_to_num(arr).mean()):.3f}) — fp16 overflow?")
        export_to_video(frames, f"{OUT}/{name}.mp4", fps=JOB["fps"])
        status[name] = {"ok": True, "seconds": round(time.time() - t0)}
    except Exception as e:
        status[name] = {"ok": False, "error": repr(e)[:500], "trace": traceback.format_exc()[-1500:]}
        torch.cuda.empty_cache()
    say(name, status[name])
    with open(f"{OUT}/status.json", "w") as f:
        json.dump({"episode_id": JOB["episode_id"], "shots": status}, f)
say("done")
