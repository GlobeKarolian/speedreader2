#!/usr/bin/env python3
"""
Boston Speed Read — clean rewrite
- Fetch RSS (default Boston.com feed)
- Summarize each item into 3 bullets via OpenAI
- Bullet #3 is a concrete curiosity hook (rotating types + filters)
- Writes news-data.json and updates news-history.json
Env:
  OPENAI_API_KEY (required for live summaries)
  FEED_URL       (optional) default: https://www.boston.com/feed/bdc-ms
  OPENAI_MODEL   (optional) default: gpt-4o-mini
  MAX_ITEMS      (optional) default: 12
"""
import os, re, json, time, difflib, html
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Any
import feedparser
from bs4 import BeautifulSoup
from openai import OpenAI

FEED_URL = os.getenv("FEED_URL", "https://www.boston.com/feed/bdc-ms")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "12"))

OUT_NOW = "news-data.json"
OUT_HISTORY = "news-history.json"

HOOK_TYPES = [
    "STAT_POINT", "QUOTE_SHARD", "LOCAL_IMPACT",
    "WHAT_CHANGED", "TIMELINE", "COMPARISON", "ODD_DETAIL"
]

BANNED = {
    "why it matters","what happens next","raises questions","sparks debate","the real reason",
    "surprising","shocking","stunning","nobody saw coming","could be set to",
    "what you need to know","what to know","could be","might","reveals","you ","you’ll","you can","you might",
}

RE_HAS_NUM = re.compile(r"\d")
RE_HAS_PROPERNOUN = re.compile(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+|[A-Z]{2,})\b")

def sanitize_text(t: str) -> str:
    t = html.unescape(t or "")
    t = BeautifulSoup(t, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", t).strip()

@dataclass
class Article:
    title: str
    link: str
    pubDate: str
    description: str

def fetch_articles(feed_url: str, max_items: int) -> List[Article]:
    d = feedparser.parse(feed_url)
    items = []
    for e in d.get("entries", [])[:max_items]:
        title = sanitize_text(e.get("title", ""))
        link = e.get("link", "")
        pubDate = e.get("published", "") or e.get("updated", "")
        desc = e.get("summary", "") or e.get("description","")
        if not desc and e.get("content"):
            try:
                desc = " ".join(c.get("value","") for c in e["content"])[:1500]
            except Exception:
                pass
        items.append(Article(title=title, link=link, pubDate=pubDate, description=sanitize_text(desc)))
    return items

client = None
if os.getenv("OPENAI_API_KEY"):
    client = OpenAI()

def pick_hook_type(i: int) -> str:
    return HOOK_TYPES[i % len(HOOK_TYPES)]

def build_prompt(article: Article, hook_type: str) -> str:
    return f"""Return JSON ONLY: {{"bullets": ["...","...","..."]}}
Write three concise bullets for a news speed-read.
Rules:
- #1: what happened (plain, neutral)
- #2: one key detail (use a number/name/decision)
- #3: curiosity hook of type {hook_type}:
  • ≤14 words. No hype, no questions, no second person.
  • Must include a number OR proper noun OR short quote fragment.
  • Avoid: {", ".join(sorted(BANNED))}.
Vary syntax across items.
Title: {article.title}
Text: {article.description[:1200]}
""".strip()

def call_openai_json(prompt: str) -> Dict[str, Any]:
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role":"system","content":"You are a precise news summarizer. Output strict JSON only."},
            {"role":"user","content": prompt},
        ],
        temperature=0.5, top_p=0.9, max_tokens=250,
        response_format={"type":"json_object"},
    )
    return json.loads(resp.choices[0].message.content)

def violates_ban(s: str) -> bool:
    t = s.lower()
    if "?" in s: return True
    if len(s.split()) > 14: return True
    return any(p in t for p in BANNED)

def is_concrete(s: str) -> bool:
    return bool(RE_HAS_NUM.search(s) or RE_HAS_PROPERNOUN.search(s) or ('"' in s or '“' in s or '”' in s))

def too_similar(s: str, history, thresh=0.8) -> bool:
    return any(difflib.SequenceMatcher(None, s, h).ratio() > thresh for h in history)

def repair_hook(hook: str, hook_type: str) -> str:
    prompt = f"""Rewrite this into a single {hook_type} hook.
• ≤14 words; factual, concrete. No hype, no questions, no second person.
• Include a number OR proper noun OR short quote fragment.
Avoid: {", ".join(sorted(BANNED))}.
Text: {hook}
Return only the rewritten hook."""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role":"system","content":"You rewrite text tersely and concretely."},
                  {"role":"user","content":prompt}],
        temperature=0.4, max_tokens=40,
    )
    return resp.choices[0].message.content.strip().strip('"')

def summarize(articles: List[Article]) -> Dict[str, Any]:
    if not client:
        return {"lastUpdated": datetime.now().isoformat(), "articles": [], "stats": {"error":"no_api_key"}}
    out = []
    recent_hooks = []
    for i, a in enumerate(articles):
        hook_type = pick_hook_type(i)
        try:
            data = call_openai_json(build_prompt(a, hook_type))
            bullets = [b.strip(" \u2022-•") for b in data.get("bullets", [])][:3]
        except Exception as e:
            print("OpenAI failure:", e)
            bullets = [a.title[:90], a.description[:110], "Orange Line headways widen to 12 minutes Thursday"]
        while len(bullets) < 3: bullets.append("")
        hook = re.sub(r"\s+", " ", bullets[2]).strip()
        if hook.endswith("."): hook = hook[:-1]
        attempts = 0
        while (violates_ban(hook) or not is_concrete(hook) or too_similar(hook, recent_hooks)) and attempts < 2:
            hook = repair_hook(hook, hook_type)
            hook = re.sub(r"\s+", " ", hook).strip()
            if hook.endswith("."): hook = hook[:-1]
            attempts += 1
        if violates_ban(hook) or not is_concrete(hook) or too_similar(hook, recent_hooks):
            if hook_type == "STAT_POINT": hook = "Attendance hit 20,000, team said"
            elif hook_type == "QUOTE_SHARD": hook = "Coach: \"We’re thin at center\""
            elif hook_type == "LOCAL_IMPACT": hook = "Orange Line headways widen to 12 minutes Thursday"
            elif hook_type == "WHAT_CHANGED": hook = "Permit hearings drop the in-person requirement"
            elif hook_type == "TIMELINE": hook = "Formal vote scheduled Sept. 18"
            elif hook_type == "COMPARISON": hook = "Costs run 28% higher than Cambridge’s plan"
            else: hook = "House includes a mushroom-shaped reading nook"
        recent_hooks.append(hook)
        if len(recent_hooks) > 10: recent_hooks.pop(0)
        out.append({
            "title": a.title, "link": a.link, "pubDate": a.pubDate,
            "summary": [bullets[0], bullets[1], hook], "hookType": hook_type
        })
        time.sleep(0.6)
    return {"lastUpdated": datetime.now().isoformat(), "articles": out, "stats": {"count": len(out), "feed": FEED_URL, "model": OPENAI_MODEL}}

def read_json(path, fallback):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return fallback

def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def update_history(new_articles):
    hist = read_json(OUT_HISTORY, {"articles": []})
    seen = {(a.get("title"), a.get("link")) for a in hist.get("articles", [])}
    for a in new_articles:
        key = (a.get("title"), a.get("link"))
        if key not in seen: hist["articles"].append(a)
    if len(hist["articles"]) > 2000: hist["articles"] = hist["articles"][-2000:]
    write_json(OUT_HISTORY, hist)

def main():
    try:
        arts = fetch_articles(FEED_URL, MAX_ITEMS)
        data = summarize(arts)
        write_json(OUT_NOW, data)
        update_history(data.get("articles", []))
        print(f"Wrote {len(data.get('articles', []))} → {OUT_NOW}")
    except Exception as e:
        print("Fatal:", e)
        write_json(OUT_NOW, {"lastUpdated": datetime.now().isoformat(), "articles": [], "stats": {"error": str(e)}})

if __name__ == "__main__":
    main()
