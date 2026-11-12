"""Hugging Face provider: LTX-2 Turbo public Space (Gradio HTTP API), image + line audio → lip-synced clip.
The owner liked this result. Free ZeroGPU quota with HF_TOKEN ≈ 2–3 shots/day, ~3 s per shot.
Shots run one by one inside submit(); when the daily quota runs out the rest are returned as `quota`
so they are retried on a later run without counting as a failed attempt."""
from __future__ import annotations

import json, os, time
from pathlib import Path
from typing import Dict, List

import requests

from . import Provider

SPACE = os.environ.get("HF_VIDEO_SPACE", "https://alexnasa-ltx-2-turbo.hf.space")
NEG_STYLE = ("3D Pixar-style Egyptian cartoon, warm cinematic light, the speaking character talks with natural lip sync "
             "to the speech, other characters listen with closed mouths, keep every character's face and clothes exactly the same.")


class QuotaExceeded(RuntimeError):
    pass


def _hdr() -> dict:
    t = os.environ.get("HF_TOKEN")
    return {"Authorization": f"Bearer {t}"} if t else {}


def render(frame: str, audio: str, prompt: str, out: Path, w: int = 576, h: int = 1024) -> Path:
    api = f"{SPACE}/gradio_api"
    up = lambda f: {"path": requests.post(f"{api}/upload", files=[("files", open(f, "rb"))], headers=_hdr(), timeout=120).json()[0],
                    "meta": {"_type": "gradio.FileData"}}
    data = [up(frame), None, prompt, None, "Image-to-Video", False, 10, True, h, w, "No LoRA", up(audio)]
    eid = requests.post(f"{api}/call/generate_video", json={"data": data}, headers=_hdr(), timeout=60).json()["event_id"]
    with requests.get(f"{api}/call/generate_video/{eid}", headers=_hdr(), stream=True, timeout=1500) as r:
        ev = None
        for line in r.iter_lines(decode_unicode=True):
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:") and ev in ("complete", "error"):
                d = line[5:].strip()
                if ev == "error":
                    if "quota" in d.lower():
                        raise QuotaExceeded(d[:300])
                    raise RuntimeError(f"space error: {d[:300]}")
                res = json.loads(d)[0]
                v = res.get("video", res) if isinstance(res, dict) else None
                if not v or not v.get("url"):
                    raise RuntimeError("space returned no video")
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(requests.get(v["url"], headers=_hdr(), timeout=300).content)
                return out
    raise RuntimeError("space stream ended without a result")


class HFProvider(Provider):
    name = "hf"

    def submit(self, episode_id: int, shots: List[dict], workdir: Path) -> str:
        results: Dict[int, dict] = {}
        quota = False
        for s in shots:
            if quota:
                results[s["idx"]] = {"ok": False, "quota": True, "error": "حصة Hugging Face اليومية خلصت"}
                continue
            dst = workdir / f"shot_{s['idx']:02d}.mp4"
            try:
                render(s["frame_path"], s["audio_path"], f"{s['prompt']} {NEG_STYLE}", dst)
                results[s["idx"]] = {"ok": True, "path": str(dst)}
            except QuotaExceeded:
                quota = True
                results[s["idx"]] = {"ok": False, "quota": True, "error": "حصة Hugging Face اليومية خلصت"}
            except Exception as e:
                results[s["idx"]] = {"ok": False, "error": str(e)[:300]}
        (workdir / "hf_job.json").write_text(json.dumps(results, ensure_ascii=False))
        return f"hf:{workdir}:{int(time.time())}"

    def poll(self, job_id: str) -> str:
        return "complete"

    def collect(self, job_id: str, workdir: Path) -> Dict[int, dict]:
        return {int(k): v for k, v in json.loads((workdir / "hf_job.json").read_text()).items()}
