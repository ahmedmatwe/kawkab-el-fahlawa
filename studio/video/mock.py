from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from ..config import settings
from ..media import run
from . import Provider


def still_clip(frame_path: str, dst: Path, mark: bool = True) -> Path:
    """Slow zoom over a still frame. Used by the demo provider and as the last-resort fallback for a shot
    that failed generation twice (flagged in QA, never hidden)."""
    g = settings()["generation"]
    secs = g["frames"] / g["fps"]
    box = ",drawbox=x=0:y=0:w=110:h=34:color=red@0.8:t=fill" if mark else ""
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(["-loop", "1", "-i", frame_path, "-t", f"{secs:.2f}", "-vf",
         f"scale={g['gen_width'] * 2}:-2,zoompan=z='1+0.0015*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
         f"s={g['gen_width']}x{g['gen_height']}:fps={g['fps']}{box}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(dst)])
    return dst


class MockProvider(Provider):
    """DEMO ONLY: slow zoom over the approved first frame + a 'DEMO' tag. Not real animation."""
    name = "mock"

    def submit(self, episode_id: int, shots: List[dict], workdir: Path) -> str:
        out = {}
        for s in shots:
            dst = workdir / f"shot_{s['idx']:02d}.mp4"
            if s.get("simulate_failure"):
                out[s["idx"]] = {"ok": False, "error": "simulated failure"}
                continue
            still_clip(s["frame_path"], dst)
            out[s["idx"]] = {"ok": True, "path": str(dst)}
        (workdir / "mock_job.json").write_text(json.dumps(out))
        return f"mock:{workdir}"

    def poll(self, job_id: str) -> str:
        return "complete"

    def collect(self, job_id: str, workdir: Path) -> Dict[int, dict]:
        return {int(k): v for k, v in json.loads((workdir / "mock_job.json").read_text()).items()}
