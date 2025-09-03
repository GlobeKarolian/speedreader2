# Boston Speed Read (clean rewrite)

A minimal, reliable AI-powered reader that pulls the Boston.com feed, writes 3 bullets per story, and **rotates concrete curiosity hooks** (Bullet #3) without clickbait.

## What’s new
- **Hook rotation** across `STAT_POINT`, `QUOTE_SHARD`, `LOCAL_IMPACT`, `WHAT_CHANGED`, `TIMELINE`, `COMPARISON`, `ODD_DETAIL`.
- **Banned-phrase filter** + **similarity guard** + **length cap** for Bullet #3.
- **Repair pass** to rewrite weak hooks.
- Clean HTML with error states (no more blank page).

## One-time setup
1. Add repository **secret**: `OPENAI_API_KEY`.
2. (Optional) Add **variables**: `FEED_URL` (default Boston.com RSS), `OPENAI_MODEL` (default `gpt-4o-mini`), `MAX_ITEMS` (default 12).
3. Enable **Pages** → Deploy from `main` (root).

## Local run
```bash
pip install -r requirements.txt
OPENAI_API_KEY=sk-... python generate_summaries.py
python -m http.server 8000  # then open http://localhost:8000
```

## Files
- `generate_summaries.py` — fetch + summarize + hook enforcement
- `index.html` — renders JSON with clear errors
- `.github/workflows/update.yml` — regenerates every 30 minutes
- `requirements.txt`

## Troubleshooting
- Blank page? Ensure `news-data.json` exists at repo root (run locally once or wait for Action). Check DevTools → Network.
- No articles? Confirm `OPENAI_API_KEY` secret; see Actions logs for API errors.

