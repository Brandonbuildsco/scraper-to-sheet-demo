# Scheduled scraper → spreadsheet

> **Demo / sample build. Not client work.** It runs against [books.toscrape.com](https://books.toscrape.com), a public sandbox site made for scraping practice, to show how I build this kind of job.

Every morning this scraper visits all 50 catalogue pages, collects every item (title, price, stock status, rating, link) and saves it as a spreadsheet. It compares the new data with the previous run and writes a short report of what changed.

It runs on a schedule on GitHub's servers. Nobody has to press anything.

## What you get out of it

| File | What's in it |
|---|---|
| [`data/latest.csv`](data/latest.csv) | Today's full list, one row per item. Opens in Excel or Google Sheets. |
| [`data/history.csv`](data/history.csv) | Every run appended with a timestamp, for trends over time |
| [`data/changes.md`](data/changes.md) | Plain-English summary: price moves, stock changes, new or removed items |
| Google Sheet *(optional)* | The same rows pushed straight into a sheet you share with the bot |

## How it's built to keep running

- **Retries:** if a page fails to load, it tries again (waiting 1s, then 2s) before giving up.
- **Polite:** it waits 1 second between pages and identifies itself with a clear user agent.
- **Logs everything:** each step is written to `logs/scraper.log`.
- **Fails loudly:** if anything breaks, or the site's layout changes and 0 items come back, the run is marked failed and GitHub emails the owner.
- **Tested:** the parser is checked against saved sample pages before every run (`tests/`), so a broken parser never overwrites good data.

## Run it yourself

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scraper.py                  # takes about a minute
python -m pytest -q                # optional: run the tests
```

## Runbook (plain English)

- **Change the schedule:** edit the `cron` line in `.github/workflows/daily-scrape.yml`. `17 11 * * *` means 11:17 UTC every day.
- **Run it right now:** Actions tab → *Daily scrape* → **Run workflow**.
- **Turn on Google Sheets:**
  1. Create a Google Cloud service account and download its JSON key.
  2. Share your sheet with the service account's email, as Editor.
  3. Add two repository secrets: `GOOGLE_SERVICE_ACCOUNT_JSON` (the whole key text) and `GOOGLE_SHEET_ID` (the long ID in the sheet's URL).
- **Point it at a different site:** change `START_URL` and the selectors in `parse_page()` in `scraper.py`. Check the site's terms and robots.txt first.
- **If a run fails:** open the failed run in the Actions tab. The red step and the log show what broke. The usual cause is a site layout change, which means updating the selectors in `parse_page()`.

## Tech

Python · Requests · BeautifulSoup · gspread (Google Sheets API) · pytest · GitHub Actions (scheduled)

---

Built by [brandonbuildsco](https://github.com/Brandonbuildsco). Want this for your own data source? Hire me on Upwork or Fiverr: **brandonbuildsco**.
