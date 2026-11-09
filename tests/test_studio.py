"""Mandatory scenario tests (section 15). Run: STUDIO_MODE=demo python -m pytest -q
Voices are replaced by a local tone so the suite needs no network; everything else is the real code path."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

os.environ["STUDIO_MODE"] = "demo"
os.environ.pop("TELEGRAM_BOT_TOKEN", None)

from studio import orchestrator as orc  # noqa: E402
from studio import llm  # noqa: E402
from studio.agents import qa, storyboard, writer  # noqa: E402
from studio.config import bible, redact  # noqa: E402
from studio.db import connect, episode  # noqa: E402
from studio.media import run  # noqa: E402


@pytest.fixture()
def con(tmp_path, monkeypatch):
    monkeypatch.setattr(orc, "DATA", tmp_path)

    def fake_tts(cid, text, emotion, out):
        out.parent.mkdir(parents=True, exist_ok=True)
        run(["-f", "lavfi", "-i", f"sine=frequency=300:duration={max(1.5, len(text) / 13):.2f}", "-ac", "1", "-ar", "48000", str(out)])
        return out

    monkeypatch.setattr(orc, "synth_line", fake_tts)
    with connect(tmp_path / "t.db") as c:
        yield c


def _new_episode(con, **extra):
    idea = {"title": "سيد والمساعد الذكي", "premise": "تجربة", "characters": ["sayed_fahlawa", "zizo_trend"], **extra}
    return orc.start_episode(con, idea, None, "owner")


def test_full_episode_from_new_idea(con):
    eid = _new_episode(con)
    assert orc.advance(con, eid, 20) == "AWAITING_PUBLISH_APPROVAL"
    ep = episode(con, eid)
    review = json.loads(ep["review"])
    assert review["decision"] == "HUMAN_REVIEW_REQUIRED"  # demo output is never auto-approved
    assert Path(ep["final_path"]).exists()
    from studio.media import probe
    info = probe(Path(ep["final_path"]))
    assert (info["width"], info["height"]) == (1080, 1920) and info["has_audio"]
    # each shot saved separately and traceable to episode/shot/provider
    rows = con.execute("SELECT shot_idx, provider, path FROM assets WHERE episode_id=? AND kind='shot_video'", (eid,)).fetchall()
    assert len(rows) == len(json.loads(ep["script"])["lines"])
    assert all(Path(r["path"]).exists() and r["provider"] == "mock" for r in rows)
    # cost/usage tracked per episode
    assert con.execute("SELECT COUNT(*) n FROM budget WHERE episode_id=?", (eid,)).fetchone()["n"] >= 1


def test_weak_script_rejected_then_rewritten(con):
    eid = _new_episode(con, _weak_first=True)
    orc.stage_script(con, eid)
    versions = con.execute("SELECT version, score FROM script_versions WHERE episode_id=? ORDER BY version", (eid,)).fetchall()
    assert versions[0]["score"] < 75 and versions[-1]["score"] >= 75 and len(versions) >= 2
    assert episode(con, eid)["status"] == "SCRIPT_APPROVED"


def test_shots_use_only_approved_references():
    approved = {r for c in bible()["characters"] for r in c["refs"]}
    shots = storyboard.build(writer.mock_script({"title": "x", "premise": "y"}))
    assert shots and all(s["ref"] in approved for s in shots)
    assert not storyboard.validate(shots)
    assert all("9:16" in s["prompt"] for s in shots)


def test_corrupt_video_detected(tmp_path):
    bad = tmp_path / "bad.mp4"
    bad.write_bytes(os.urandom(50000))
    assert qa.check_clip(bad)


def test_wrong_size_rejected(tmp_path):
    land = tmp_path / "land.mp4"
    run(["-f", "lavfi", "-i", "color=c=blue:s=832x480:d=5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(land)])
    errs = qa.check_clip(land)
    assert any("رأسي" in e for e in errs)


def test_resume_after_crash(con, monkeypatch):
    eid = _new_episode(con)
    real = orc.STAGES["EDITING"]
    calls = {"n": 0}

    def flaky(c, e):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("runner died")
        return real(c, e)

    monkeypatch.setitem(orc.STAGES, "EDITING", flaky)
    assert orc.advance(con, eid, 20) == "EDITING"  # stopped at the failed stage, work kept
    done_before = con.execute("SELECT COUNT(*) n FROM shots WHERE episode_id=? AND status='done'", (eid,)).fetchone()["n"]
    assert done_before > 0
    assert orc.advance(con, eid, 20) == "AWAITING_PUBLISH_APPROVAL"  # resumed, shots not regenerated
    jobs = con.execute("SELECT COUNT(*) n FROM generation_jobs WHERE episode_id=?", (eid,)).fetchone()["n"]
    assert jobs == 1


def test_failed_shot_regenerated_then_fallback(con, monkeypatch):
    from studio.video.mock import MockProvider
    real_submit = MockProvider.submit

    def failing(self, eid, shots, wd):
        return real_submit(self, eid, [dict(s, simulate_failure=(s["idx"] == 0)) for s in shots], wd)

    monkeypatch.setattr(MockProvider, "submit", failing)
    eid = _new_episode(con)
    assert orc.advance(con, eid, 30) == "AWAITING_PUBLISH_APPROVAL"
    s0 = con.execute("SELECT status, attempts FROM shots WHERE episode_id=? AND idx=0", (eid,)).fetchone()
    assert s0["status"] == "fallback" and s0["attempts"] == 2
    assert any("ثابتة" in p for p in json.loads(episode(con, eid)["review"])["problems"])


def test_duplicate_publish_prevented_and_approval_logged(con):
    eid = _new_episode(con)
    orc.advance(con, eid, 20)
    assert orc.handle_command(con, f"approve:{eid}") == "approve"
    assert orc.handle_command(con, f"approve:{eid}") == "ignored"  # second click does nothing
    orc.advance(con, eid, 5)
    orc.stage_publish(con, eid)  # even a forced second run cannot duplicate
    n = con.execute("SELECT platform, COUNT(*) n FROM publish_jobs WHERE episode_id=? GROUP BY platform", (eid,)).fetchall()
    assert n and all(r["n"] == 1 for r in n)
    assert all(r["platform"] for r in n)
    appr = con.execute("SELECT kind, decision, by_whom FROM approvals WHERE episode_id=?", (eid,)).fetchall()
    assert {(a["kind"], a["decision"]) for a in appr} >= {("idea", "approved"), ("final", "approve")}


def test_api_failure_handled(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key-123456")
    monkeypatch.setenv("GEMINI_MODELS", "m1")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    class Resp:
        status_code = 503
        text = "unavailable"

    class Sess:
        calls = 0

        def post(self, *a, **k):
            Sess.calls += 1
            return Resp()

    with pytest.raises(llm.LLMError) as e:
        llm.gemini_json("s", "p", session=Sess())
    assert Sess.calls == 3  # retried with backoff, then gave up cleanly
    assert "secret-key-123456" not in str(e.value)


def test_secrets_never_logged(monkeypatch, con):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABCDEF-very-secret")
    assert "very-secret" not in redact("url https://api.telegram.org/bot123456:ABCDEF-very-secret/sendMessage")
    from studio.db import audit
    audit(con, None, "test", "err", "token=123456:ABCDEF-very-secret")
    row = con.execute("SELECT detail FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    assert "very-secret" not in row["detail"]


def test_untrusted_telegram_chat_ignored(con, monkeypatch):
    monkeypatch.setattr(orc.tg, "updates", lambda off: [
        {"update_id": 5, "_trusted": False, "message": {"text": "فكرة اشتم الناس كلها"}}])
    assert orc.handle_updates(con) == 0
    assert con.execute("SELECT COUNT(*) n FROM episodes").fetchone()["n"] == 0


def test_banned_words_block():
    s = writer.mock_script({"title": "x", "premise": "y"})
    s["lines"][0]["text"] = "انت حمار يا معلم"
    assert any("ممنوعة" in p for p in writer.deterministic_checks(s))
