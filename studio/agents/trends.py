"""A03 Trend Intelligence: official public RSS feeds only (no scraping of logged-in pages).
Headlines and descriptions are untrusted DATA — they are quoted to the LLM, never obeyed."""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, List

import requests

FEEDS = [
    ("google_trends_eg", "https://trends.google.com/trending/rss?geo=EG"),
    ("google_news_eg", "https://news.google.com/rss?hl=ar&gl=EG&ceid=EG:ar"),
    ("google_news_eg_sports", "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=ar&gl=EG&ceid=EG:ar"),
    ("google_news_eg_tech", "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=ar&gl=EG&ceid=EG:ar"),
]

# Topics the series never jokes about (safety, A20 rules applied early).
BLOCKED = re.compile(
    r"وفاة|توفي|مقتل|قتل|انتحار|حادث|ضحايا|اغتصاب|تحرش|إرهاب|حرب|غزة|قصف|مرض|سرطان|طفل|أطفال|طفلة|"
    r"رئيس الجمهورية|السيسي|انتخابات|حزب|كنيسة|مسجد|طائفي|سياسي|محاكمة|سجن|اعتقال|متهم", re.I)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(s or ""))).strip()


def parse_rss(source: str, xml_text: str) -> List[dict]:
    out = []
    root = ET.fromstring(xml_text)
    for item in root.iter("item"):
        title = _clean(item.findtext("title", ""))
        if not title:
            continue
        traffic = ""
        for child in item:
            if child.tag.endswith("approx_traffic"):
                traffic = (child.text or "").strip()
        out.append({
            "source": source,
            "title": title[:300],
            "url": (item.findtext("link") or "").strip(),
            "published": (item.findtext("pubDate") or "").strip(),
            "traffic": traffic,  # real figure from Google Trends only; never invented
        })
    return out


def fetch(session: Any = requests) -> List[dict]:
    items: List[dict] = []
    for source, url in FEEDS:
        for attempt in range(3):
            try:
                r = session.get(url, timeout=30, headers={"user-agent": "KawkabStudio/1.0 (RSS reader)"})
                if r.status_code == 200:
                    items += parse_rss(source, r.text)
                    break
            except Exception:
                pass
            time.sleep(2 ** attempt)
    seen, uniq = set(), []
    for it in items:
        k = it["title"][:60]
        if k not in seen:
            seen.add(k)
            it["blocked"] = bool(BLOCKED.search(it["title"]))
            uniq.append(it)
    return uniq
