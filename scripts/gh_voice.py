"""Egyptian-colloquial speech from the public ahmedmatwe/egyptian-tts repo (free, unlimited GitHub Actions minutes).
Usage: python scripts/gh_voice.py "النص" OUT.wav [--exaggeration 0.6] [--seed 7]
Uses the `gh` CLI. Locally it uses your gh login; inside GitHub Actions set GH_TOKEN to a token that can run
workflows on ahmedmatwe/egyptian-tts (secret EGY_TTS_TOKEN). The audio artifact is deleted right after download."""
import argparse, glob, json, shutil, subprocess, tempfile, time, uuid
REPO = "ahmedmatwe/egyptian-tts"
gh = lambda *a: subprocess.run(["gh", *a], check=True, capture_output=True, text=True).stdout

ap = argparse.ArgumentParser(); ap.add_argument("text"); ap.add_argument("out")
ap.add_argument("--exaggeration", default="0.6"); ap.add_argument("--seed", default="7")
a = ap.parse_args()
rid = uuid.uuid4().hex[:10]
gh("workflow", "run", "speak", "-R", REPO, "-f", f"text={a.text}", "-f", f"request_id={rid}",
   "-f", f"exaggeration={a.exaggeration}", "-f", f"seed={a.seed}")
run = None
for _ in range(30):
    runs = json.loads(gh("run", "list", "-R", REPO, "-w", "speak", "-L", "20", "--json", "databaseId,displayTitle"))
    run = next((r["databaseId"] for r in runs if r["displayTitle"] == f"speak {rid}"), None)
    if run: break
    time.sleep(4)
if not run: raise SystemExit("run not found")
subprocess.run(["gh", "run", "watch", str(run), "-R", REPO, "--exit-status", "--interval", "15"], check=True, capture_output=True)
with tempfile.TemporaryDirectory() as d:
    gh("run", "download", str(run), "-R", REPO, "-D", d)
    shutil.copy(glob.glob(f"{d}/**/speech-{rid}.wav", recursive=True)[0], a.out)
for art in json.loads(gh("api", f"repos/{REPO}/actions/runs/{run}/artifacts"))["artifacts"]:
    gh("api", "-X", "DELETE", f"repos/{REPO}/actions/artifacts/{art['id']}")
print("saved", a.out, "run", run)
