#!/usr/bin/env bash
# Persist studio state (SQLite + per-episode frames/voices/finished shot clips) between cloud runs.
# The state lives in the PRIVATE repo $STATE_REPO (default ahmedmatwe/kawkab-state), reached with $STATE_TOKEN
# (fine-grained token: Contents read/write on that repo only). This repo can therefore be public (free, unlimited
# Actions minutes) while episode data stays private. Final videos are not stored (Telegram + artifacts).
set -euo pipefail
cmd=${1:?load|save}
REPO=${STATE_REPO:-ahmedmatwe/kawkab-state}
: "${STATE_TOKEN:?STATE_TOKEN secret missing (token for the private state repo)}"
URL="https://x-access-token:${STATE_TOKEN}@github.com/${REPO}.git"
rm -rf .state
if [ "$cmd" = load ]; then
  if git clone -q --depth 1 "$URL" .state 2>/dev/null; then
    mkdir -p data && cp -R .state/data/. data/ 2>/dev/null || true
  fi
  rm -rf .state
  echo "state loaded: $(ls data 2>/dev/null | tr '\n' ' ')"
elif [ "$cmd" = save ]; then
  git clone -q --depth 1 "$URL" .state 2>/dev/null || { mkdir -p .state && git -C .state init -q -b main && git -C .state remote add origin "$URL"; }
  mkdir -p .state/data
  rsync -a --delete --prune-empty-dirs --include='*/' --include='studio.db' \
    --include='*.jpg' --include='*.wav' --include='shot_*.mp4' --include='*.json' --include='*.ass' --include='*.srt' --exclude='*' data/ .state/data/
  cd .state
  git add -A data
  if git diff --cached --quiet; then echo "no state change"; else
    git -c user.name="kawkab-studio" -c user.email="studio@users.noreply.github.com" commit -qm "state $(date -u +%FT%TZ)"
    git push -q origin HEAD:main
  fi
  cd .. && rm -rf .state
fi
