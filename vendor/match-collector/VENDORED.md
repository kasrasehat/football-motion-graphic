# Vendored: match-collector 0.1.0

Copied unchanged from the user's project at `E:\codex_files\web scrapper` (handoff ZIP of 2026-11-06). This repo runs without that folder.
To update: replace these files from a new handoff, reinstall with `.venv/Scripts/python.exe -m pip install ./vendor/match-collector`, and run `tms verify`.
Its FastAPI service (`api.py`) is not used here: `engine/tms/research/scrape.py` calls `collect()` directly.

## Source notes (checked 2026-11-05)
- **Access:** one honest user agent, robots.txt obeyed, paced requests, no stealth or challenge bypass. Keep it that way.
- **Soccerway:** its terms (2.2, 2.9, 2.10) bar commercial use, extraction and scraping without Livesport's consent. Reads Livesport feed hosts too. The user chooses per project; each run's sources are logged in the decision log.
- **Sofascore:** returned HTTP 403, and its site shows a human-verification check. Reported as blocked; nothing tries to get past it.
- **ballhelper:** robots.txt 404, no terms found; betting-tips site, so low trust. Plain HTTP only (its HTTPS certificate does not match).
