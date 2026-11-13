#!/usr/bin/env bash
# Persist studio state (SQLite + small per-episode files) on the `state` branch between cloud runs.
# Finished shot clips (shot_*.mp4, ~1–3 MB) ARE kept so a fresh runner can edit the episode; final videos are not
# (they go to Telegram + artifacts). Without this a later run would replace lost shots with still frames.
set -euo pipefail
cmd=${1:?load|save}
if [ "$cmd" = load ]; then
  if git fetch -q origin state 2>/dev/null; then
    rm -rf .state && git worktree add -q .state origin/state
    mkdir -p data && cp -R .state/data/. data/ 2>/dev/null || true
    git worktree remove --force .state
  fi
  echo "state loaded: $(ls data 2>/dev/null | tr '\n' ' ')"
elif [ "$cmd" = save ]; then
  rm -rf .state
  if git fetch -q origin state 2>/dev/null; then git worktree add -q -B state .state origin/state
  else git worktree add -q --orphan -b state .state 2>/dev/null || { git worktree add -q --detach .state && (cd .state && git checkout -q --orphan state && git rm -rqf . || true); }; fi
  mkdir -p .state/data
  rsync -a --delete --prune-empty-dirs --include='*/' --include='studio.db' \
    --include='*.jpg' --include='*.wav' --include='shot_*.mp4' --include='*.json' --include='*.ass' --include='*.srt' --exclude='*' data/ .state/data/
  cd .state
  git add -A data
  if git diff --cached --quiet; then echo "no state change"; else
    git -c user.name="kawkab-studio" -c user.email="studio@users.noreply.github.com" commit -qm "state $(date -u +%FT%TZ)"
    git push -q origin state
  fi
fi
