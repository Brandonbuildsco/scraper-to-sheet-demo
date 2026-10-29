"""
Scheduled scraper -> spreadsheet  (DEMO / SAMPLE BUILD - not client work)

What it does, start to finish:
  1. Visits every catalogue page of https://books.toscrape.com
     (a public sandbox site built for scraping practice).
  2. Pulls title, price, stock status, star rating and link for every book.
  3. Saves the results to data/latest.csv and appends a dated copy
     to data/history.csv so you can see changes over time.
  4. Compares today's prices with the previous run and writes a short
     summary of what changed to data/changes.md.
  5. (Optional) Pushes the same rows into a Google Sheet if credentials
     are provided.
  6. Logs every step to logs/scraper.log and exits with an error code
     if something breaks, so the scheduler can alert you.

Run it:  python scraper.py
"""

import csv
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Settings - change these to point the scraper at a different job
# ---------------------------------------------------------------------------
START_URL = "https://books.toscrape.com/catalogue/page-1.html"
DELAY_SECONDS = 1.0          # pause between pages so we don't hammer the site
MAX_RETRIES = 3              # how many times to retry a page that fails
TIMEOUT_SECONDS = 20         # give up on a single request after this long
USER_AGENT = "brandonbuildsco-demo-scraper/1.0 (+https://github.com/Brandonbuildsco)"

DATA_DIR = Path("data")
LOG_DIR = Path("logs")
LATEST_CSV = DATA_DIR / "latest.csv"
HISTORY_CSV = DATA_DIR / "history.csv"
CHANGES_MD = DATA_DIR / "changes.md"

FIELDS = ["scraped_at", "title", "price_gbp", "in_stock", "rating", "url"]

# The site stores star ratings as words in a CSS class ("star-rating Three").
RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


# ---------------------------------------------------------------------------
# Logging: write to the screen AND to logs/scraper.log
# ---------------------------------------------------------------------------
def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    logger = logging.getLogger("scraper")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s  %(levelname)-7s %(message)s")
    for handler in (logging.StreamHandler(sys.stdout),
                    logging.FileHandler(LOG_DIR / "scraper.log", encoding="utf-8")):
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    return logger


log = setup_logging()


# ---------------------------------------------------------------------------
# Step 1: download a page, retrying if the network hiccups
# ---------------------------------------------------------------------------
def fetch(session: requests.Session, url: str) -> str:
    """Return the HTML of `url`. Retries with a growing wait (1s, 2s, 4s...)."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(url, timeout=TIMEOUT_SECONDS)
            response.raise_for_status()          # turns 404/500 into an error
            response.encoding = "utf-8"          # the site is UTF-8 (the £ sign)
            return response.text
        except requests.RequestException as err:
            wait = 2 ** (attempt - 1)
            log.warning("Attempt %d/%d failed for %s: %s", attempt, MAX_RETRIES, url, err)
            if attempt == MAX_RETRIES:
                raise                            # out of retries - let it fail loudly
            time.sleep(wait)
    raise RuntimeError("unreachable")            # keeps type checkers happy


# ---------------------------------------------------------------------------
# Step 2: turn one page of HTML into a list of book rows
# ---------------------------------------------------------------------------
def parse_page(html: str, page_url: str, scraped_at: str):
    """Return (rows, next_page_url). next_page_url is None on the last page."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for card in soup.select("article.product_pod"):
        link = card.select_one("h3 a")
        price_text = card.select_one(".price_color").get_text(strip=True)   # e.g. "£51.77"
        rating_classes = card.select_one(".star-rating")["class"]           # ["star-rating", "Three"]
        rating_word = next((c for c in rating_classes if c in RATING_WORDS), None)

        rows.append({
            "scraped_at": scraped_at,
            "title": link["title"].strip(),
            "price_gbp": float(price_text.lstrip("£Â")),   # keep just the number
            "in_stock": "In stock" in card.select_one(".availability").get_text(),
            "rating": RATING_WORDS.get(rating_word, 0),
            "url": urljoin(page_url, link["href"]),         # make the link absolute
        })

    next_link = soup.select_one("li.next a")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return rows, next_url


# ---------------------------------------------------------------------------
# Step 3: walk every page until there is no "next" button
# ---------------------------------------------------------------------------
def scrape_all(start_url: str = START_URL):
    scraped_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    all_rows, url, page = [], start_url, 0
    while url:
        page += 1
        rows, url = parse_page(fetch(session, url), url, scraped_at)
        all_rows.extend(rows)
        log.info("Page %d: %d books (running total %d)", page, len(rows), len(all_rows))
        if url:
            time.sleep(DELAY_SECONDS)
    return all_rows


# ---------------------------------------------------------------------------
# Step 4: save to CSV files
# ---------------------------------------------------------------------------
def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows, append: bool = False):
    path.parent.mkdir(exist_ok=True)
    is_new = not path.exists() or not append
    with path.open("a" if append else "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# Step 5: compare with the last run and describe what changed
# ---------------------------------------------------------------------------
def summarize_changes(previous, current) -> str:
    """Build a short Markdown report: price moves, stock changes, new/removed items."""
    old = {r["url"]: r for r in previous}
    new = {r["url"]: r for r in current}
    lines = []

    for url, row in new.items():
        before = old.get(url)
        if before is None:
            continue
        old_price, new_price = float(before["price_gbp"]), float(row["price_gbp"])
        if abs(old_price - new_price) >= 0.01:
            lines.append(f"- Price: **{row['title']}** £{old_price:.2f} → £{new_price:.2f}")
        if str(before["in_stock"]) != str(row["in_stock"]):
            status = "back in stock" if row["in_stock"] else "now out of stock"
            lines.append(f"- Stock: **{row['title']}** {status}")

    added = new.keys() - old.keys()
    removed = old.keys() - new.keys()
    if previous and added:
        lines.append(f"- {len(added)} new item(s) listed")
    if removed:
        lines.append(f"- {len(removed)} item(s) no longer listed")

    stamp = current[0]["scraped_at"] if current else "n/a"
    header = f"# Changes since last run\n\nRun: {stamp} · Items: {len(current)}\n\n"
    if not previous:
        return header + "First run - nothing to compare yet.\n"
    return header + ("\n".join(lines) + "\n" if lines else "No changes.\n")


# ---------------------------------------------------------------------------
# Step 6 (optional): push to Google Sheets
# ---------------------------------------------------------------------------
def push_to_google_sheet(rows):
    """
    Only runs if both environment variables are set:
      GOOGLE_SERVICE_ACCOUNT_JSON  - the service account key (the JSON text)
      GOOGLE_SHEET_ID              - the ID from the sheet's URL
    Share the sheet with the service account's email (Editor) first.
    """
    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")
    if not creds_json or not sheet_id:
        log.info("Google Sheets not configured - skipped (CSV still saved).")
        return

    import gspread  # imported here so the CSV-only setup doesn't need it

    client = gspread.service_account_from_dict(json.loads(creds_json))
    worksheet = client.open_by_key(sheet_id).sheet1
    values = [FIELDS] + [[r[f] for f in FIELDS] for r in rows]
    worksheet.clear()
    worksheet.update(values, "A1")
    log.info("Google Sheet updated with %d rows.", len(rows))


# ---------------------------------------------------------------------------
# Main: run every step; exit with code 1 on any failure so alerts fire
# ---------------------------------------------------------------------------
def main() -> int:
    log.info("Run started.")
    try:
        previous = read_csv(LATEST_CSV)
        rows = scrape_all()
        if not rows:
            raise RuntimeError("Scraped 0 rows - the site layout may have changed.")

        write_csv(LATEST_CSV, rows)
        write_csv(HISTORY_CSV, rows, append=True)
        CHANGES_MD.write_text(summarize_changes(previous, rows), encoding="utf-8")
        push_to_google_sheet(rows)

        log.info("Run finished: %d items saved to %s.", len(rows), LATEST_CSV)
        return 0
    except Exception:
        log.exception("Run FAILED.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
