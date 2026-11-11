"""Egyptian-colloquial voices from the public ahmedmatwe/egyptian-tts repo (free, unlimited GitHub Actions minutes).
One workflow run voices a whole batch of lines. Needs the `gh` CLI with access: locally your gh login; inside
GitHub Actions the secret EGY_TTS_TOKEN (exported as GH_TOKEN). The artifact is deleted right after download."""
from __future__ import annotations

import glob, json, os, shutil, subprocess, tempfile, time, uuid
from pathlib import Path
from typing import Dict, List

REPO = os.environ.get("EGY_TTS_REPO", "ahmedmatwe/egyptian-tts")
EMOTION_EX = {"angry": 0.85, "surprised": 0.8, "happy": 0.7, "laughing": 0.8, "sad": 0.45, "thinking": 0.45}


def _gh(*a: str, timeout: int = 120) -> str:
    env = dict(os.environ)
    if env.get("EGY_TTS_TOKEN"):
        env["GH_TOKEN"] = env["EGY_TTS_TOKEN"]
    return subprocess.run(["gh", *a], check=True, capture_output=True, text=True, timeout=timeout, env=env).stdout


def available() -> bool:
    if os.environ.get("EGY_TTS", "1") == "0" or os.environ.get("STUDIO_MODE") == "demo" or not shutil.which("gh"):
        return False
    if os.environ.get("GITHUB_ACTIONS") and not os.environ.get("EGY_TTS_TOKEN"):
        return False
    try:
        _gh("api", f"repos/{REPO}", "-q", ".id", timeout=30)
        return True
    except Exception:
        return False


def synth_batch(items: List[Dict], timeout_s: int = 1800) -> None:
    """items: [{"character", "text", "emotion", "out": Path}] → writes each out as WAV (24 kHz)."""
    if not items:
        return
    rid = uuid.uuid4().hex[:10]
    lines = [{"id": f"l{i:03d}", "text": it["text"], "voice": it["character"],
              "exaggeration": EMOTION_EX.get(it.get("emotion", ""), 0.6)} for i, it in enumerate(items)]
    _gh("workflow", "run", "speak", "-R", REPO, "-f", f"batch={json.dumps(lines, ensure_ascii=False)}", "-f", f"request_id={rid}")
    run = None
    for _ in range(40):
        runs = json.loads(_gh("run", "list", "-R", REPO, "-w", "speak", "-L", "30", "--json", "databaseId,displayTitle"))
        run = next((r["databaseId"] for r in runs if r["displayTitle"] == f"speak {rid}"), None)
        if run:
            break
        time.sleep(5)
    if not run:
        raise RuntimeError("egyptian-tts run did not start")
    _gh("run", "watch", str(run), "-R", REPO, "--exit-status", "--interval", "20", timeout=timeout_s)
    try:
        with tempfile.TemporaryDirectory() as d:
            _gh("run", "download", str(run), "-R", REPO, "-D", d, timeout=300)
            for ln, it in zip(lines, items):
                src = glob.glob(f"{d}/**/{ln['id']}.wav", recursive=True)
                if not src:
                    raise RuntimeError(f"missing voice for line {ln['id']}")
                Path(it["out"]).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src[0], it["out"])
    finally:
        for art in json.loads(_gh("api", f"repos/{REPO}/actions/runs/{run}/artifacts"))["artifacts"]:
            _gh("api", "-X", "DELETE", f"repos/{REPO}/actions/artifacts/{art['id']}")
