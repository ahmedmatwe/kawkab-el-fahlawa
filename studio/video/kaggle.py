"""Real shot generation on Kaggle's free GPU (≈30 GPU-hours/week, phone-verified account).
Uses only the official Kaggle CLI: `kernels push`, `kernels status`, `kernels output`.
Auth: KAGGLE_API_TOKEN (new style) or KAGGLE_USERNAME + KAGGLE_KEY — from GitHub Secrets, never written to logs."""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

from ..config import ROOT, env, redact, settings
from . import Provider

SLUG = "kawkab-render"


def _cli(*args: str, timeout: int = 600) -> str:
    p = subprocess.run([sys.executable, "-m", "kaggle.cli", *args], capture_output=True, text=True, timeout=timeout)
    out = redact((p.stdout or "") + (p.stderr or ""))
    if p.returncode != 0:
        raise RuntimeError(f"kaggle {args[0]} {args[1] if len(args) > 1 else ''} failed: {out[-800:]}")
    return out


def username() -> str:
    u = env("KAGGLE_USERNAME")
    if u:
        return u
    out = _cli("config", "view")
    m = re.search(r"username:\s*(\S+)", out)
    if not m:
        raise RuntimeError("KAGGLE_USERNAME not set")
    return m.group(1)


class KaggleProvider(Provider):
    name = "kaggle"

    def submit(self, episode_id: int, shots: List[dict], workdir: Path) -> str:
        g = settings()["generation"]
        job = {
            "episode_id": episode_id, "model": g["model"], "width": g["gen_width"], "height": g["gen_height"],
            "frames": g["frames"], "fps": g["fps"], "steps": g["steps"],
            "shots": [{"idx": s["idx"], "prompt": s["prompt"], "negative": s["negative"],
                       "frame_b64": base64.b64encode(Path(s["frame_path"]).read_bytes()).decode()} for s in shots],
        }
        kdir = workdir / "kaggle_kernel"
        kdir.mkdir(parents=True, exist_ok=True)
        tpl = (ROOT / "studio/video/kernel_template.py").read_text(encoding="utf-8")
        code = tpl.replace("__JOB_B64__", base64.b64encode(json.dumps(job).encode()).decode())
        (kdir / "render.py").write_text(code, encoding="utf-8")
        user = username()
        (kdir / "kernel-metadata.json").write_text(json.dumps({
            "id": f"{user}/{SLUG}", "title": SLUG, "code_file": "render.py", "language": "python",
            "kernel_type": "script", "is_private": True, "enable_gpu": True, "enable_internet": True,
            "dataset_sources": [], "competition_sources": [], "kernel_sources": [], "model_sources": [],
        }))
        _cli("kernels", "push", "-p", str(kdir))
        return f"{user}/{SLUG}#ep{episode_id}"

    def poll(self, job_id: str) -> str:
        ref = job_id.split("#")[0]
        out = _cli("kernels", "status", ref).lower()
        for word, state in (("complete", "complete"), ("error", "error"), ("cancel", "error"),
                            ("running", "running"), ("queued", "queued")):
            if word in out:
                return state
        return "running"

    def collect(self, job_id: str, workdir: Path) -> Dict[int, dict]:
        ref = job_id.split("#")[0]
        dst = workdir / "kaggle_out"
        dst.mkdir(parents=True, exist_ok=True)
        _cli("kernels", "output", ref, "-p", str(dst), "--force", timeout=1800)
        status_file = dst / "status.json"
        status = json.loads(status_file.read_text()).get("shots", {}) if status_file.exists() else {}
        result: Dict[int, dict] = {}
        for name, st in status.items():
            idx = int(name.split("_")[1])
            path = dst / f"{name}.mp4"
            ok = bool(st.get("ok")) and path.exists()
            result[idx] = {"ok": ok, "path": str(path) if ok else "", "error": st.get("error", "" if ok else "missing file")}
        return result
