import json
import time

from ..db import audit


def log_task(con, episode_id, agent, status, decision="", output=None, error="", started=None):
    """Every agent run is recorded (inputs summarised, decision, error) for the dashboard/audit."""
    con.execute(
        "INSERT INTO agent_tasks(episode_id,agent,status,decision,output,error,started,finished) VALUES(?,?,?,?,?,?,?,?)",
        (episode_id, agent, status, decision,
         json.dumps(output, ensure_ascii=False)[:20000] if output is not None else None,
         str(error)[:2000], started or time.time(), time.time()))
    audit(con, episode_id, agent, status, decision or error)
