"""A01 Executive Producer — the resumable workflow engine.
`tick()` is safe to run any number of times (cron every few minutes in the cloud): it reads Telegram replies,
sends the morning ideas, and advances every open episode by as many stages as it can.
A stage only runs when the previous one is recorded as done in SQLite, so a crash resumes from the last good stage."""
from __future__ import annotations

import datetime as dt
import json
import time
import traceback
from pathlib import Path
from typing import List, Optional

from . import telegram as tg
from .agents import ideas as ideas_agent
from .agents import consistency, log_task, producer, qa, safety, storyboard, trends, writer
from .audio import synth_line, synth_lines
from .config import DATA, demo_mode, settings
from .db import audit, connect, episode, jload, kv_get, kv_set, now, set_status
from .edit import assemble
from .video import get_provider

OPEN = ("SCRIPT_DRAFT", "SCRIPT_APPROVED", "STORYBOARD_READY", "GENERATING", "EDITING", "QA_PENDING", "APPROVED")


def local_now() -> dt.datetime:
    return dt.datetime.utcnow() + dt.timedelta(hours=settings()["timezone_offset_hours"])


def today() -> str:
    return local_now().strftime("%Y-%m-%d")


def epdir(eid: int) -> Path:
    p = DATA / "episodes" / f"ep_{eid:04d}"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ───────────────────────── morning: trends → ideas → Telegram ─────────────────────────
def morning(con, force: bool = False) -> int:
    s = settings()
    if not force:
        if local_now().hour < s["morning_hour"] or kv_get(con, "ideas_sent_day") == today():
            return 0
        made_today = con.execute("SELECT COUNT(*) n FROM episodes WHERE day=?", (today(),)).fetchone()["n"]
        if made_today >= s["episodes_per_day"]:
            return 0
    t0 = time.time()
    items = trends.fetch() if not demo_mode() else []
    for it in items[:60]:
        con.execute("INSERT INTO trends(day,title,source,url,published,category,score,risk,created) VALUES(?,?,?,?,?,?,?,?,?)",
                    (today(), it["title"], it["source"], it["url"], it["published"], "", 0,
                     "blocked" if it["blocked"] else "", now()))
    recent = [r["title"] for r in con.execute("SELECT json_extract(data,'$.title') title FROM ideas ORDER BY id DESC LIMIT 40")]
    ideas = ideas_agent.propose(items, recent, s["ideas_per_morning"])
    log_task(con, None, "A03+A02+A04", "done", f"{len(items)} trends → {len(ideas)} ideas", ideas, started=t0)
    tg.send(f"☀️ صباح الفهلوة! ده اقتراحات حلقة النهارده ({today()}).\n"
            "اختار فكرة بالزرار، أو اضغط «أفكار تانية»، أو ابعت فكرتك برسالة تبدأ بكلمة: فكرة")
    for i, idea in enumerate(ideas, 1):
        cur = con.execute("INSERT INTO ideas(day,data,status,created) VALUES(?,?,?,?)",
                          (today(), json.dumps(idea, ensure_ascii=False), "proposed", now()))
        iid = cur.lastrowid
        mid = tg.send(ideas_agent.format_for_telegram(i, idea), [[("🎬 ابدأ الفكرة دي", f"pick:{iid}")]])
        con.execute("UPDATE ideas SET message_id=? WHERE id=?", (mid, iid))
    tg.send("مش عاجباك؟", [[("🔄 أفكار تانية", "more")]])
    kv_set(con, "ideas_sent_day", today())
    return len(ideas)


# ───────────────────────── Telegram replies ─────────────────────────
def episode_mode() -> str:
    """production = real LLM + real video. pilot = pre-written script but REAL video/voices (no DEMO stamp).
    demo = everything mocked (stamped DEMO)."""
    if not demo_mode():
        return "production"
    return "pilot" if get_provider().name != "mock" else "demo"


def start_episode(con, idea: dict, idea_id: Optional[int], by: str) -> int:
    cur = con.execute("INSERT INTO episodes(day,status,mode,idea,created,updated) VALUES(?,?,?,?,?,?)",
                      (today(), "SCRIPT_DRAFT", episode_mode(),
                       json.dumps(idea, ensure_ascii=False), now(), now()))
    eid = cur.lastrowid
    if idea_id:
        con.execute("UPDATE ideas SET status='picked', episode_id=? WHERE id=?", (eid, idea_id))
    con.execute("INSERT INTO approvals(episode_id,kind,decision,by_whom,created) VALUES(?,?,?,?,?)",
                (eid, "idea", "approved", by, now()))
    audit(con, eid, by, "idea_approved", idea.get("title", ""))
    return eid


def handle_updates(con) -> int:
    offset = int(kv_get(con, "tg_offset", "0") or 0)
    n = 0
    done = []
    for u in tg.updates(offset):
        if "update_id" in u and "_queue_key" not in u:
            kv_set(con, "tg_offset", u["update_id"] + 1)
        if "_queue_key" in u:
            done.append(u["_queue_key"])
        if not u["_trusted"]:
            audit(con, None, "telegram", "ignored_untrusted_chat", "")
            continue
        n += 1
        try:
            if u.get("_kind") == "start_episode":
                start_from_brief(con, u.get("brief") or {})
                continue
            cb = u.get("callback_query")
            if cb:
                handle_command(con, cb.get("data", ""), cb_id=cb["id"])
            elif (u.get("message") or {}).get("text"):
                handle_text(con, u["message"]["text"].strip())
        finally:
            con.commit()
    tg.queue_ack(done)
    tg.queue_status(eta_text(con))
    return n


def start_from_brief(con, b: dict) -> int:
    idea = {"title": b.get("title") or (b.get("premise") or "حلقة")[:40],
            "premise": (b.get("premise") or "") + (f"\nتفاصيل متفق عليها مع صاحب القناة: {b['details']}" if b.get("details") else ""),
            "characters": b.get("characters") or ["sayed_fahlawa", "zizo_trend"], "location": b.get("location", "cafe"),
            "trend_title": "", "fact_basis": "", "risk": "low", "source": "owner_chat"}
    return start_episode(con, idea, None, "owner")


def handle_command(con, data: str, cb_id: str = "") -> str:
    kind, _, arg = data.partition(":")
    if kind == "pick":
        row = con.execute("SELECT * FROM ideas WHERE id=?", (int(arg),)).fetchone()
        if not row or row["status"] == "picked":
            tg.answer_callback(cb_id, "الفكرة دي اتاخدت قبل كده")
            return "dup"
        eid = start_episode(con, json.loads(row["data"]), row["id"], "owner")
        tg.answer_callback(cb_id, "تمام! بدأنا 🎬")
        tg.send(f"🎬 حلقة #{eid} «{json.loads(row['data'])['title']}» دخلت الإنتاج. هبعتلك أول ما تخلص.")
        return f"episode:{eid}"
    if kind == "chat":
        tg.answer_callback(cb_id, "تمام")
        if arg == "cancel":
            kv_set(con, "producer_chat", "")
            tg.send("اتلغت 👍 ابعتلي في أي وقت لو عندك فكرة حلقة.")
            return "chat_cancel"
        return chat_start(con)
    if kind == "more":
        tg.answer_callback(cb_id, "ثواني…")
        kv_set(con, "ideas_sent_day", "")
        morning(con, force=True)
        return "more"
    if kind in ("approve", "redo", "reject"):
        eid = int(arg)
        ep = episode(con, eid)
        if ep["status"] != "AWAITING_PUBLISH_APPROVAL":
            tg.answer_callback(cb_id, f"الحلقة حالتها {ep['status']}")
            return "ignored"
        con.execute("INSERT INTO approvals(episode_id,kind,decision,by_whom,created) VALUES(?,?,?,?,?)",
                    (eid, "final", kind, "owner", now()))
        if kind == "approve":
            set_status(con, eid, "APPROVED")
            tg.answer_callback(cb_id, "اتعتمدت ✅")
        elif kind == "redo":
            con.execute("DELETE FROM shots WHERE episode_id=?", (eid,))
            set_status(con, eid, "SCRIPT_DRAFT", script=None, storyboard=None, attempts=0)
            tg.answer_callback(cb_id, "هنعيدها بسيناريو جديد 🔁")
        else:
            set_status(con, eid, "FAILED", error="rejected by owner")
            tg.answer_callback(cb_id, "اترفضت ❌")
        return kind
    return "unknown"


def handle_text(con, text: str) -> str:
    t = text.replace("أ", "ا")
    chat = jload(kv_get(con, "producer_chat", "") or "", {}) or {}
    if chat and t not in ("حالة", "الحالة", "status", "مساعدة", "help"):
        return chat_turn(con, text)  # we're in the middle of a conversation about an episode
    if t in ("ابدا", "ابدأ", "يلا", "start"):
        row = con.execute("SELECT id FROM ideas WHERE day=? AND status='proposed' ORDER BY id LIMIT 1", (today(),)).fetchone()
        if row:
            return handle_command(con, f"pick:{row['id']}")
        tg.send("مفيش أفكار مستنية النهارده. ابعت «غير» عشان أجيبلك أفكار.")
        return "none"
    if t.startswith("غير") or t in ("افكار", "more"):
        return handle_command(con, "more")
    if t in ("حالة", "الحالة", "status"):
        rows = con.execute("SELECT id,status,json_extract(idea,'$.title') t FROM episodes ORDER BY id DESC LIMIT 5").fetchall()
        tg.send("\n".join(f"#{r['id']} {r['t']} — {r['status']}" for r in rows) or "لسه مفيش حلقات")
        return "status"
    if t in ("مساعدة", "help", "?", "؟"):
        tg.send("اكتبلي الحلقة اللي في دماغك وهنتناقش فيها 🎬\nأو: «ابدأ» أول فكرة · «غير» أفكار تانية · «حالة» الحلقات")
        return "help"
    return chat_turn(con, text)  # anything else = the owner describing an episode → talk it through


# ───────────────────────── producer chat (owner ↔ bot about a requested episode) ─────────────────────────
SHOTS_PER_DAY = 2  # free Hugging Face ZeroGPU quota ≈ 210 s/day; one lip-sync shot asks ~100 s


def _when(ts: int) -> str:
    t = dt.datetime.utcfromtimestamp(ts) + dt.timedelta(hours=settings()["timezone_offset_hours"])
    d = (t.date() - local_now().date()).days
    day = "النهارده" if d <= 0 else "بكرة" if d == 1 else f"يوم {['الاتنين','التلات','الأربع','الخميس','الجمعة','السبت','الحد'][t.weekday()]}"
    h = t.hour % 12 or 12
    part = "الصبح" if t.hour < 12 else "الضهر" if t.hour < 15 else "العصر" if t.hour < 18 else "بالليل"
    return f"{day} الساعة {h}:{t.minute:02d} {part}"


def delivery_ts(con, eid: int) -> int:
    """When episode `eid` should reach the owner: shots ahead of it (older episodes) + its own, at SHOTS_PER_DAY,
    starting when the free video quota is back; +15 min for editing/QA."""
    def left(e):
        return con.execute("SELECT COUNT(*) n FROM shots WHERE episode_id=? AND status IN ('pending','retry','generating')",
                           (e,)).fetchone()["n"]
    ahead = sum(left(r["id"]) for r in con.execute(
        "SELECT id FROM episodes WHERE id<? AND status NOT IN ('FAILED','PUBLISHED','APPROVED','AWAITING_PUBLISH_APPROVAL')", (eid,)))
    n = ahead + max(left(eid), 1)
    start = max(now(), int(kv_get(con, "hf_retry_at", "0") or 0))
    batches = -(-n // SHOTS_PER_DAY) - 1  # first batch runs at `start`
    return int(start + batches * 86400 + 15 * 60)


def eta_text(con) -> str:
    """For the producer chat: when a new ~4-shot episode would reach the owner if we started now."""
    ahead = con.execute("SELECT COUNT(*) n FROM shots s JOIN episodes e ON e.id=s.episode_id "
                        "WHERE s.status IN ('pending','retry','generating') AND e.status NOT IN ('FAILED','PUBLISHED')").fetchone()["n"]
    queued = con.execute("SELECT COUNT(*) n FROM episodes WHERE status IN ('SCRIPT_DRAFT','SCRIPT_APPROVED')").fetchone()["n"]
    n = ahead + 4 * queued + 4
    start = max(now(), int(kv_get(con, "hf_retry_at", "0") or 0))
    ts = int(start + (-(-n // SHOTS_PER_DAY) - 1) * 86400 + 20 * 60)
    return (f"لو بدأنا دلوقتي الحلقة هتوصلك تقريبًا {_when(ts)} "
            f"(قدامها {ahead + 4 * queued} لقطة، والحصة المجانية حوالي {SHOTS_PER_DAY} لقطات في اليوم)")


def chat_turn(con, text: str) -> str:
    chat = jload(kv_get(con, "producer_chat", "") or "", {}) or {"history": [], "brief": {}}
    chat["history"].append({"role": "owner", "text": text[:1500]})
    try:
        out = producer.converse(chat["history"], chat["brief"], eta_text(con))
    except Exception as e:
        tg.send("معلش حصلت مشكلة وأنا بفكر 🙏 ابعتلي تاني كمان شوية.")
        audit(con, None, "producer", "error", str(e)[:300])
        return "chat_error"
    chat["brief"] = out["brief"]
    chat["history"].append({"role": "bot", "text": out["reply"]})
    kv_set(con, "producer_chat", json.dumps(chat, ensure_ascii=False))
    if out["ready"]:
        tg.send(out["reply"])
        return chat_start(con)
    tg.send(out["reply"], [[("✅ ابدأ الحلقة", "chat:go"), ("🗑️ إلغاء", "chat:cancel")]] if chat["brief"].get("premise") else None)
    return "chat"


def chat_start(con) -> str:
    chat = jload(kv_get(con, "producer_chat", "") or "", {}) or {}
    b = chat.get("brief") or {}
    if not b.get("premise"):
        tg.send("لسه محتاج أعرف الحلقة عن إيه 🙂 احكيلي.")
        return "chat_empty"
    idea = {"title": b.get("title") or b["premise"][:40],
            "premise": b["premise"] + (f"\nتفاصيل متفق عليها مع صاحب القناة: {b['details']}" if b.get("details") else ""),
            "characters": b.get("characters") or ["sayed_fahlawa", "zizo_trend"], "location": b.get("location", "cafe"),
            "trend_title": "", "fact_basis": "", "risk": "low", "source": "owner_chat"}
    eta = eta_text(con)
    eid = start_episode(con, idea, None, "owner")
    kv_set(con, "producer_chat", "")
    tg.send(f"🎬 حلقة #{eid} «{idea['title']}» دخلت الإنتاج.\n{eta}.\nهبعتلك الحلقة تشوفها وتوافق قبل أي نشر.")
    return f"episode:{eid}"


# ───────────────────────── production stages ─────────────────────────
def stage_script(con, eid: int) -> None:
    ep = episode(con, eid)
    idea = jload(ep["idea"], {})
    q = settings()["quality"]
    notes, best = "", None
    for version in range(1, q["max_script_rewrites"] + 2):
        t0 = time.time()
        script = writer.write(idea, notes, weak_mock=bool(idea.get("_weak_first")) and version == 1)
        script["fact_basis"] = idea.get("fact_basis", "")
        score, problems, fixes = writer.review(script)
        con.execute("INSERT INTO script_versions(episode_id,version,data,review,score,created) VALUES(?,?,?,?,?,?)",
                    (eid, version, json.dumps(script, ensure_ascii=False),
                     json.dumps({"problems": problems, "fixes": fixes}, ensure_ascii=False), score, now()))
        ok = score >= q["script_min_score"]
        log_task(con, eid, "A05+A06+A07", "done", f"v{version} score {score} {'approve' if ok else 'revise'}",
                 {"problems": problems}, started=t0)
        if not best or score > best[0]:
            best = (score, script)
        if ok:
            break
        notes = "\n".join(problems + fixes)
    score, script = best
    if score < q["script_min_score"]:
        set_status(con, eid, "MANUAL_ACTION_REQUIRED", error=f"script stuck at {score}/100", script=script)
        tg.send(f"⚠️ حلقة #{eid}: السيناريو ماوصلش للمستوى ({score}/100) بعد {q['max_script_rewrites'] + 1} محاولات. ابعت «غير» لفكرة تانية.")
        return
    verdict, issues, _ = safety.review(script)
    log_task(con, eid, "A20", "done", f"script safety {verdict}", issues)
    if verdict == "block":
        set_status(con, eid, "FAILED", error="safety: " + "; ".join(issues), script=script)
        tg.send(f"⛔ حلقة #{eid} اتوقفت لأسباب سلامة المحتوى: {'؛ '.join(issues)}")
        return
    set_status(con, eid, "SCRIPT_APPROVED", script=script, score=score)


def stage_storyboard(con, eid: int) -> None:
    script = jload(episode(con, eid)["script"])
    shots = storyboard.build(script)
    errs = storyboard.validate(shots)
    if errs:
        set_status(con, eid, "FAILED", error="; ".join(errs))
        return
    d = epdir(eid)
    for s in shots:
        s["frame_path"] = str(consistency.first_frame(s["ref"], d / f"frame_{s['idx']:02d}.jpg", s["location"]))
        wav = d / f"line_{s['idx']:02d}.wav"
        s["_wav"] = wav
    synth_lines([{"character": s["speaker"], "text": s["text"], "emotion": s["emotion"], "out": s["_wav"]} for s in shots])
    for s in shots:
        wav = s.pop("_wav")
        con.execute("INSERT OR REPLACE INTO shots(episode_id,idx,data,prompt,status,attempts,audio_path) VALUES(?,?,?,?,?,?,?)",
                    (eid, s["idx"], json.dumps(s, ensure_ascii=False), s["prompt"], "pending", 0, str(wav)))
    log_task(con, eid, "A08+A11+A09+A13", "done", f"{len(shots)} shots, frames + voices ready")
    set_status(con, eid, "STORYBOARD_READY", storyboard=shots)
    con.commit()
    title = jload(episode(con, eid)["script"], {}).get("title", "")
    tg.send(f"📝 حلقة #{eid} «{title}»: السيناريو والأصوات جاهزين ({len(shots)} لقطات).\n"
            f"🎬 بدأنا التصوير دلوقتي.\n📬 الحلقة هتوصلك تشوفها وتوافق تقريبًا {_when(delivery_ts(con, eid))}.")


def _shots(con, eid: int) -> List[dict]:
    out = []
    for r in con.execute("SELECT * FROM shots WHERE episode_id=? ORDER BY idx", (eid,)):
        s = json.loads(r["data"])
        s.update(status=r["status"], attempts=r["attempts"], video_path=r["video_path"], audio_path=r["audio_path"])
        out.append(s)
    return out


def _ensure_inputs(eid: int, shots: List[dict]) -> None:
    """Frames/voices are regenerated if the runner lost them (fresh cloud machine)."""
    d = epdir(eid)
    for s in shots:
        if not Path(s["frame_path"]).exists():
            consistency.first_frame(s["ref"], Path(s["frame_path"]), s.get("location", "alley"))
    synth_lines([{"character": s["speaker"], "text": s["text"], "emotion": s["emotion"], "out": Path(s["audio_path"])}
                 for s in shots if not Path(s["audio_path"]).exists()])


def stage_generate(con, eid: int):
    shots = [s for s in _shots(con, eid) if s["status"] in ("pending", "retry")]
    if not shots:
        set_status(con, eid, "EDITING")
        return
    if int(kv_get(con, "hf_retry_at", "0") or 0) > now():
        return "wait"  # free video quota not back yet → the next run after hf_retry_at continues
    _ensure_inputs(eid, shots)
    prov = get_provider()
    job = prov.submit(eid, shots, epdir(eid))
    con.execute("INSERT INTO generation_jobs(episode_id,provider,external_id,status,meta,started) VALUES(?,?,?,?,?,?)",
                (eid, prov.name, job, "submitted", json.dumps([s["idx"] for s in shots]), now()))
    for s in shots:
        con.execute("UPDATE shots SET status='generating', attempts=attempts+1 WHERE episode_id=? AND idx=?", (eid, s["idx"]))
    log_task(con, eid, "A12", "submitted", f"{prov.name}: {len(shots)} shots → {job}")
    set_status(con, eid, "GENERATING")


def stage_poll(con, eid: int) -> bool:
    job = con.execute("SELECT * FROM generation_jobs WHERE episode_id=? ORDER BY id DESC LIMIT 1", (eid,)).fetchone()
    prov = get_provider()
    state = prov.poll(job["external_id"])
    g = settings()["generation"]
    if state in ("queued", "running"):
        if (now() - job["started"]) / 60 > g["max_kaggle_minutes"]:
            state = "error"
        else:
            return False
    d = epdir(eid)
    results = prov.collect(job["external_id"], d) if state == "complete" else {}
    con.execute("UPDATE generation_jobs SET status=?, finished=? WHERE id=?", (state, now(), job["id"]))
    gpu_min = round((now() - job["started"]) / 60, 1)
    con.execute("INSERT INTO budget(episode_id,provider,units,usd,note,created) VALUES(?,?,?,?,?,?)",
                (eid, prov.name, gpu_min, 0.0, "GPU minutes (free quota)", now()))
    failed = []
    for s in _shots(con, eid):
        if s["status"] != "generating":
            continue
        r = results.get(s["idx"], {"ok": False, "error": f"job {state}"})
        errs = [] if not r.get("ok") else qa.check_clip(Path(r["path"]))
        if r.get("ok") and not errs:
            sim = consistency.similarity(Path(s["frame_path"]), Path(r["path"]))
            if sim < consistency.THRESHOLD:
                errs.append(f"شكل الشخصية اتغير (تشابه {sim:.2f})")
            else:
                con.execute("UPDATE shots SET status='done', video_path=?, error='' WHERE episode_id=? AND idx=?",
                            (r["path"], eid, s["idx"]))
                con.execute("INSERT INTO assets(episode_id,shot_idx,kind,path,provider,meta,created) VALUES(?,?,?,?,?,?,?)",
                            (eid, s["idx"], "shot_video", r["path"], prov.name, json.dumps({"similarity": sim}), now()))
                continue
        reason = r.get("error") or "; ".join(errs)
        if r.get("quota"):  # free daily GPU quota ran out: not the shot's fault → retry later, attempt not counted
            if r.get("retry_at"):
                kv_set(con, "hf_retry_at", max(int(kv_get(con, "hf_retry_at", "0") or 0), int(r["retry_at"])))
            con.execute("UPDATE shots SET status='retry', attempts=MAX(attempts-1,0), error=? WHERE episode_id=? AND idx=?",
                        (reason, eid, s["idx"]))
            failed.append(f"لقطة {s['idx'] + 1}: {reason}")
            continue
        final = s["attempts"] >= g["max_attempts_per_shot"]
        con.execute("UPDATE shots SET status=?, error=? WHERE episode_id=? AND idx=?",
                    ("fallback" if final else "retry", reason, eid, s["idx"]))
        failed.append(f"لقطة {s['idx'] + 1}: {reason}")
    log_task(con, eid, "A12+A09", state, f"{len(results)} clips back, {len(failed)} problems", failed)
    if any(r.get("quota") for r in results.values()):
        left = sum(1 for s in _shots(con, eid) if s["status"] in ("pending", "retry"))
        done = sum(1 for s in _shots(con, eid) if s["status"] == "done")
        tg.send(f"⏳ حلقة #{eid}: خلصنا {done} لقطة، وفاضل {left}. حصة الفيديو المجانية النهارده خلصت، "
                f"وهتتجدد {_when(int(kv_get(con, 'hf_retry_at', '0') or 0))}.\n📬 الحلقة هتوصلك تقريبًا {_when(delivery_ts(con, eid))}.")
    if any(s["status"] == "retry" for s in _shots(con, eid)):
        set_status(con, eid, "STORYBOARD_READY")  # regenerate only the failed shots
    else:
        set_status(con, eid, "EDITING")
    return True


def stage_edit(con, eid: int) -> None:
    ep = episode(con, eid)
    script = jload(ep["script"])
    shots = _shots(con, eid)
    _ensure_inputs(eid, shots)
    d = epdir(eid)
    lost = [s for s in shots if s["status"] == "done" and not (s["video_path"] and Path(s["video_path"]).exists())]
    if lost:  # a finished clip didn't survive between cloud runs → render it again, never cover it with a still
        for s in lost:
            con.execute("UPDATE shots SET status='retry', video_path=NULL, error=? WHERE episode_id=? AND idx=?",
                        ("الفيديو اتفقد بين التشغيلات — هيتعمل تاني", eid, s["idx"]))
        log_task(con, eid, "A16", "retry", f"{len(lost)} finished clips missing → re-render")
        set_status(con, eid, "STORYBOARD_READY")
        return "wait"
    clips = []
    for s in shots:
        if s["status"] == "done" and s["video_path"] and Path(s["video_path"]).exists():
            clips.append(Path(s["video_path"]))
        else:  # failed after max attempts → animated still of the approved frame, flagged in QA
            from .video.mock import still_clip
            clips.append(still_clip(s["frame_path"], d / "fallback" / f"shot_{s['idx']:02d}.mp4", mark=False))
    final = assemble(d, script["title"], script["lines"], clips, [Path(s["audio_path"]) for s in shots],
                     demo=ep["mode"] == "demo")
    con.execute("INSERT INTO assets(episode_id,kind,path,provider,created) VALUES(?,?,?,?,?)",
                (eid, "final_video", str(final), "ffmpeg", now()))
    log_task(con, eid, "A16+A17+A14", "done", f"final {final.name}")
    set_status(con, eid, "QA_PENDING", final_path=str(final))


def stage_qa(con, eid: int) -> None:
    ep = episode(con, eid)
    script = jload(ep["script"])
    final = Path(ep["final_path"])
    vqa = qa.visual_audio_qa(final)
    sims = []
    fallbacks = 0
    for a in con.execute("SELECT meta FROM assets WHERE episode_id=? AND kind='shot_video'", (eid,)):
        sims.append(jload(a["meta"], {}).get("similarity", 0))
    for s in _shots(con, eid):
        if s["status"] != "done":
            fallbacks += 1
            sims.append(0.0)
    if fallbacks:
        vqa = (max(vqa[0] - 4 * fallbacks, 0), vqa[1], vqa[2], vqa[3] + [f"{fallbacks} لقطة صورة ثابتة بدل فيديو"])
    saf = safety.review(script)
    decision, total, breakdown = qa.final_decision(int(ep["score"] or 0), sims, vqa, saf, ep["mode"] != "production")
    con.execute("INSERT INTO agent_tasks(episode_id,agent,status,decision,output,started,finished) VALUES(?,?,?,?,?,?,?)",
                (eid, "A21", "done", decision, json.dumps(breakdown, ensure_ascii=False), now(), now()))
    set_status(con, eid, "AWAITING_PUBLISH_APPROVAL" if decision != "REJECTED" else "FAILED",
               review=dict(breakdown, decision=decision, total=total))
    if decision == "REJECTED":
        tg.send(f"⛔ حلقة #{eid} اترفضت في المراجعة: {'؛ '.join(breakdown['problems'])}")
        return
    meta = script.get("metadata", {})
    probs = "\n".join(f"• {p}" for p in breakdown["problems"]) or "• مفيش"
    cap = (f"🎬 حلقة #{eid}: {script['title']}\n📊 الجودة {total}/100 — {decision}\n"
           f"سيناريو {breakdown['script']}/20 · ثبات {breakdown['consistency']}/20 · صورة {breakdown['animation']}/20 · "
           f"صوت {breakdown['audio']}/15 · مونتاج {breakdown['edit']}/10 · سلامة {breakdown['safety']}/15\n"
           f"ملاحظات:\n{probs}\n\n📝 {meta.get('title', '')}")
    tg.send_video(final, cap, [[("✅ اعتمد", f"approve:{eid}"), ("🔁 أعد", f"redo:{eid}"), ("❌ ارفض", f"reject:{eid}")]])


def stage_publish(con, eid: int) -> None:
    """A24: auto-publish is OFF by default → prepare a manual publishing pack, never post twice."""
    ep = episode(con, eid)
    script = jload(ep["script"])
    meta = script.get("metadata", {})
    pub = settings()["publishing"]
    for p in pub["platforms"]:
        con.execute("INSERT OR IGNORE INTO publish_jobs(episode_id,platform,status,error,created) VALUES(?,?,?,?,?)",
                    (eid, p, "MANUAL_PUBLISH_REQUIRED",
                     "auto_publish off / account not connected" if not pub["auto_publish"] else "connector not built yet", now()))
    tags = " ".join(meta.get("hashtags", []))
    tg.send(f"📤 حلقة #{eid} جاهزة للنشر اليدوي (الفيديو في الرسالة اللي فوق):\n\n"
            f"العنوان: {meta.get('title', script['title'])}\n\nالوصف: {meta.get('description', '')}\n{tags}\n\n"
            "⚠️ فعّل علامة «محتوى معدّل/مولّد بالذكاء الاصطناعي» في كل منصة.")
    set_status(con, eid, "MANUAL_ACTION_REQUIRED", error="MANUAL_PUBLISH_REQUIRED")


STAGES = {
    "SCRIPT_DRAFT": stage_script,
    "SCRIPT_APPROVED": stage_storyboard,
    "STORYBOARD_READY": stage_generate,
    "EDITING": stage_edit,
    "QA_PENDING": stage_qa,
    "APPROVED": stage_publish,
}


def advance(con, eid: int, max_steps: int = 10) -> str:
    for _ in range(max_steps):
        st = episode(con, eid)["status"]
        try:
            if st == "GENERATING":
                if not stage_poll(con, eid):
                    con.commit()
                    break
                con.commit()  # keep collected shots even if a later stage crashes
                continue
            fn = STAGES.get(st)
            if not fn:
                break
            if fn(con, eid) == "wait":
                con.commit()
                break
            con.commit()
        except Exception as e:
            con.rollback()
            n = (episode(con, eid)["attempts"] or 0) + 1
            err = f"{st}: {e}"
            log_task(con, eid, "A01", "error", err, error=traceback.format_exc()[-1500:])
            con.execute("UPDATE episodes SET attempts=?, error=? WHERE id=?", (n, err[:1000], eid))
            if n >= 4:
                set_status(con, eid, "FAILED", error=err[:1000])
                tg.send(f"❌ حلقة #{eid} وقفت في مرحلة {st}: {str(e)[:300]}")
            con.commit()
            break
    return episode(con, eid)["status"]


def tick() -> dict:
    with connect() as con:
        n_up = handle_updates(con)
        con.commit()
        n_ideas = morning(con)
        con.commit()
        out = {}
        for r in con.execute(f"SELECT id FROM episodes WHERE status IN ({','.join('?' * len(OPEN))}) ORDER BY id",
                             OPEN).fetchall():
            out[r["id"]] = advance(con, r["id"])
        con.commit()
        tg.queue_status(eta_text(con), wake_at=int(kv_get(con, "hf_retry_at", "0") or 0) if out else 0)
        return {"updates": n_up, "ideas": n_ideas, "episodes": out}
