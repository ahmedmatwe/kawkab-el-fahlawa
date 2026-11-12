"""CLI:  python -m studio tick | inbox | morning | demo | status | agents | pick <idea_id> | cmd <callback-data>"""
from __future__ import annotations

import json
import sys

from . import orchestrator as orc
from .agents.registry import AGENTS
from .config import demo_mode
from .db import connect


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "tick"
    if cmd == "tick":
        print(json.dumps(orc.tick(), ensure_ascii=False))
    elif cmd == "inbox":  # quick run triggered by the Cloudflare inbox: process queued Telegram messages only
        with connect() as con:
            print(orc.handle_updates(con), "messages handled")
    elif cmd == "morning":
        with connect() as con:
            print(orc.morning(con, force=True), "ideas sent")
    elif cmd == "demo":
        if not demo_mode():
            sys.exit("demo needs STUDIO_MODE=demo")
        with connect() as con:
            n = orc.morning(con, force=True)
            iid = con.execute("SELECT id FROM ideas ORDER BY id DESC LIMIT ?", (n,)).fetchall()[-1]["id"]
            ref = orc.handle_command(con, f"pick:{iid}")
            eid = int(ref.split(":")[1])
            print("episode", eid, "→", orc.advance(con, eid, max_steps=20))
            print(json.dumps(dict(con.execute("SELECT review, final_path FROM episodes WHERE id=?", (eid,)).fetchone()),
                             ensure_ascii=False, indent=1))
    elif cmd == "cmd":
        with connect() as con:
            print(orc.handle_command(con, argv[2]))
    elif cmd == "status":
        with connect() as con:
            for r in con.execute("SELECT id, day, status, mode, json_extract(idea,'$.title') t, error FROM episodes ORDER BY id DESC LIMIT 20"):
                print(dict(r))
    elif cmd == "agents":
        for a in AGENTS:
            print(" | ".join(a))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv)
