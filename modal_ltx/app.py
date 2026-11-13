"""LTX-2 (19B, distilled + audio lip-sync) on Modal — the same pipeline as the LTX-2 Turbo HF Space the owner liked,
trimmed to what a talking cartoon shot needs (distilled LoRA + static-camera LoRA, no pose/depth/canny).
  .venv-modal/bin/modal run modal_ltx/app.py::download          # once, CPU only: models → Volume "kawkab-models"
  .venv-modal/bin/modal run modal_ltx/app.py --scene DIR          # DIR/shots.json + frames/wavs → DIR/out/*.mp4
"""
import json, os, pathlib, time
import modal

app = modal.App("kawkab-ltx2")
vol = modal.Volume.from_name("kawkab-models", create_if_missing=True)
MODELS = "/models"
SPACE = "alexnasa/ltx-2-TURBO"

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-cudnn-devel-ubuntu22.04", add_python="3.12")
    .apt_install("git", "ffmpeg", "libgl1", "libglib2.0-0")
    .pip_install("torch==2.8.0", "torchvision==0.23.0", "torchaudio==2.8.0")
    .pip_install("einops", "numpy", "transformers==5.0.0", "safetensors", "accelerate", "flashpack==0.1.2",
                 "scikit-image>=0.25.2", "imageio", "imageio-ffmpeg", "av", "tqdm", "pillow", "scipy>=1.14",
                 "bitsandbytes==0.49.1", "opencv-python-headless", "controlnet_aux", "matplotlib", "dwpose",
                 "gradio", "spaces", "huggingface_hub[hf_xet]")
    .run_commands(f"python -c \"from huggingface_hub import snapshot_download; snapshot_download('{SPACE}', repo_type='space', local_dir='/app', allow_patterns=['*.py','packages/**'])\"")
)

FILES = [("Lightricks/LTX-2", "ltx-2-19b-dev.safetensors"),
         ("Lightricks/LTX-2", "ltx-2-spatial-upscaler-x2-1.0.safetensors"),
         ("Lightricks/LTX-2", "ltx-2-19b-distilled-lora-384.safetensors"),
         ("Lightricks/LTX-2-19b-LoRA-Camera-Control-Static", "ltx-2-19b-lora-camera-control-static.safetensors")]
GEMMA = "google/gemma-3-12b-it-qat-q4_0-unquantized"


@app.function(image=image, volumes={MODELS: vol}, secrets=[modal.Secret.from_name("kawkab-hf")], timeout=3 * 3600, cpu=4)
def download():
    from huggingface_hub import hf_hub_download, snapshot_download
    for repo, f in FILES:
        d = f"{MODELS}/{repo.replace('/', '__')}"
        if not os.path.exists(f"{d}/{f}"):
            print("downloading", repo, f, flush=True); hf_hub_download(repo, f, local_dir=d)
            vol.commit()
    snapshot_download(GEMMA, local_dir=f"{MODELS}/{GEMMA.replace('/', '__')}")
    vol.commit()
    for p in sorted(pathlib.Path(MODELS).rglob("*.safetensors")):
        print(round(p.stat().st_size / 1e9, 1), "GB", p)


def _load_space_module():
    """Run the Space's app.py up to the UI (no Gradio demo, no example caching), with a trimmed LoRA set."""
    src = open("/app/app.py").read()
    src = src[: src.index('\ncss = """')]
    import re
    lo = src.index("static_lora_path = get_hub_or_local_checkpoint(")
    hi = src.index("# Load distilled LoRA as a regular LoRA")
    src = src[:lo] + '''static_lora_path = get_hub_or_local_checkpoint(
    "Lightricks/LTX-2-19b-LoRA-Camera-Control-Static", "ltx-2-19b-lora-camera-control-static.safetensors")
''' + src[hi:]
    lo = src.index("loras = [")
    hi = src.index("]", src.index("LoraPathStrengthAndSDOps(depth_lora_path")) + 1
    src = src[:lo] + '''loras = [
    LoraPathStrengthAndSDOps(path=distilled_lora_path, strength=0.6, sd_ops=LTXV_LORA_COMFY_RENAMING_MAP),
    LoraPathStrengthAndSDOps(static_lora_path, DEFAULT_LORA_STRENGTH, LTXV_LORA_COMFY_RENAMING_MAP),
]''' + src[hi:]
    src = src.replace('depth_processor = MidasDetector.from_pretrained("lllyasviel/Annotators").to("cuda")', "depth_processor = None")
    src = src.replace('APP_ROOT / "hf_models"', f'Path("{MODELS}")')
    ns = {"__name__": "ltx_space", "__file__": "/app/app.py"}
    exec(compile(src, "/app/app.py", "exec"), ns)
    return ns


@app.function(image=image, gpu="H200", volumes={MODELS: vol}, timeout=40 * 60)
def render_scene(shots: list) -> list:
    t0 = time.time()
    ns = _load_space_module()
    print(f"models loaded in {time.time() - t0:.0f}s", flush=True)
    outs = []
    for s in shots:
        t = time.time()
        fr, au = f"/tmp/f{s['idx']}.jpg", f"/tmp/a{s['idx']}.wav"
        open(fr, "wb").write(s["frame"]); open(au, "wb").write(s["audio"])
        try:
            res = ns["generate_video"](fr, None, s["prompt"], float(s["duration"]), None, "Image-to-Video", False,
                                       int(s.get("seed", 7)), False, int(s.get("height", 1024)), int(s.get("width", 576)),
                                       "No LoRA", au)
            path = res[0] if isinstance(res, (list, tuple)) else res
            path = path.get("video", path) if isinstance(path, dict) else path
            outs.append({"idx": s["idx"], "ok": True, "mp4": open(path, "rb").read(), "secs": round(time.time() - t)})
        except Exception as e:
            import traceback; traceback.print_exc()
            outs.append({"idx": s["idx"], "ok": False, "error": repr(e)[:400], "secs": round(time.time() - t)})
        print(f"shot {s['idx']}: {outs[-1]['ok']} in {outs[-1]['secs']}s", flush=True)
    return outs


@app.local_entrypoint()
def main(scene: str):
    d = pathlib.Path(scene)
    shots = json.loads((d / "shots.json").read_text())
    for s in shots:
        s["frame"] = (d / s["frame_file"]).read_bytes(); s["audio"] = (d / s["audio_file"]).read_bytes()
    t = time.time()
    res = render_scene.remote(shots)
    (d / "out").mkdir(exist_ok=True)
    for r in res:
        if r["ok"]:
            (d / "out" / f"shot_{r['idx']:02d}.mp4").write_bytes(r["mp4"])
        print(r["idx"], "ok" if r["ok"] else r["error"], r["secs"], "s")
    print(f"total {time.time() - t:.0f}s")
