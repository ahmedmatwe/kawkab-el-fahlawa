#!/usr/bin/env bash
# يحفظ مفاتيحك كـ GitHub Secrets من غير ما تظهر في الشاشة أو في أي ملف.
# التشغيل: scripts/connect.sh   (من جوه فولدر المشروع)
set -euo pipefail
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo "المستودع: $repo"
ask() { local name=$1 label=$2; read -rsp "$label (Enter = تخطي): " v; echo; [ -n "$v" ] && printf '%s' "$v" | gh secret set "$name" -R "$repo" && echo "  ✓ $name"; return 0; }
ask TELEGRAM_BOT_TOKEN "توكن بوت تليجرام من @BotFather"
ask TELEGRAM_CHAT_ID  "رقم الشات بتاعك (ابعت /start للبوت وبعدين افتح https://api.telegram.org/bot<TOKEN>/getUpdates)"
ask GEMINI_API_KEY    "مفتاح Gemini من aistudio.google.com"
ask KAGGLE_USERNAME   "اسم المستخدم في Kaggle"
ask KAGGLE_KEY        "Kaggle API key (من kaggle.json أو Settings → API)"
echo "خلاص. شغّل: gh workflow run studio.yml -f command=morning"
