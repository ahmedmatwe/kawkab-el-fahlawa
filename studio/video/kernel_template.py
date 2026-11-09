# Kawkab El Fahlawa — shot renderer that runs on a free Kaggle GPU.
# Generated per episode by studio/video/kaggle.py: the JOB below (prompts + base64 first frames) is filled in.
# Model: Wan 2.2 TI2V-5B (Apache-2.0, open weights) through Hugging Face diffusers, image-to-video.
import base64, io, json, os, subprocess, sys, time, traceback

JOB = json.loads(base64.b64decode("__JOB_B64__").decode("utf-8"))
OUT = "/kaggle/working"
os.environ.setdefault("HF_HOME", "/tmp/hf")
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
dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
vae = AutoencoderKLWan.from_pretrained(JOB["model"], subfolder="vae", torch_dtype=torch.float32)
pipe = WanImageToVideoPipeline.from_pretrained(JOB["model"], vae=vae, torch_dtype=dtype)
pipe.enable_model_cpu_offload()
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
        frames = pipe(image=img, prompt=shot["prompt"], negative_prompt=shot["negative"],
                      height=JOB["height"], width=JOB["width"], num_frames=JOB["frames"],
                      num_inference_steps=JOB["steps"], guidance_scale=5.0,
                      generator=torch.Generator("cpu").manual_seed(1000 + shot["idx"])).frames[0]
        export_to_video(frames, f"{OUT}/{name}.mp4", fps=JOB["fps"])
        status[name] = {"ok": True, "seconds": round(time.time() - t0)}
    except Exception as e:
        status[name] = {"ok": False, "error": repr(e)[:500], "trace": traceback.format_exc()[-1500:]}
        torch.cuda.empty_cache()
    say(name, status[name])
    with open(f"{OUT}/status.json", "w") as f:
        json.dump({"episode_id": JOB["episode_id"], "shots": status}, f)
say("done")
