"""A12 Animation Production: one interface, swappable providers.
- mock   : demo only — animates the approved first frame with a slow zoom (labelled DEMO).
- hf     : LTX-2 Turbo on a public Hugging Face Space — image + line audio → lip-synced clip (default).
- kaggle : real generation on Kaggle's free GPU via the official Kaggle API/CLI (kernels push/status/output).
A provider never claims a capability it lacks: submit() → poll() → collect()."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

from ..config import demo_mode, env


class Provider:
    name = "base"

    def submit(self, episode_id: int, shots: List[dict], workdir: Path) -> str:
        raise NotImplementedError

    def poll(self, job_id: str) -> str:
        """Returns queued | running | complete | error."""
        raise NotImplementedError

    def collect(self, job_id: str, workdir: Path) -> Dict[int, dict]:
        """Returns {shot_idx: {"ok": bool, "path": str, "error": str}}."""
        raise NotImplementedError


def get_provider() -> Provider:
    name = env("VIDEO_PROVIDER", "mock" if demo_mode() else "hf")
    if name == "hf":
        from .hf import HFProvider
        return HFProvider()
    if name == "kaggle":
        from .kaggle import KaggleProvider
        return KaggleProvider()
    from .mock import MockProvider
    return MockProvider()
