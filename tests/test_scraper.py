"""
Offline tests: they use small saved HTML samples instead of the live site,
so they run in a second and never hit the network.

Run them with:  python -m pytest -q
"""

import scraper

# Two tiny pages shaped exactly like the real site's markup.
PAGE_1 = """
<html><body><ol class="row">
  <li><article class="product_pod">
    <p class="star-rating Three"></p>
    <h3><a href="a-light-in-the-attic_1000/index.html" title="A Light in the Attic">A Light...</a></h3>
    <div class="product_price"><p class="price_color">£51.77</p>
    <p class="instock availability">In stock</p></div>
  </article></li>
  <li><article class="product_pod">
    <p class="star-rating One"></p>
    <h3><a href="tipping-the-velvet_999/index.html" title="Tipping the Velvet">Tipping...</a></h3>
    <div class="product_price"><p class="price_color">£53.74</p>
    <p class="availability">Out of stock</p></div>
  </article></li>
</ol><ul class="pager"><li class="current">Page 1 of 2</li>
<li class="next"><a href="page-2.html">next</a></li></ul></body></html>
"""

PAGE_2 = """
<html><body><ol class="row">
  <li><article class="product_pod">
    <p class="star-rating Five"></p>
    <h3><a href="soumission_998/index.html" title="Soumission">Soumission</a></h3>
    <div class="product_price"><p class="price_color">£50.10</p>
    <p class="instock availability">In stock</p></div>
  </article></li>
</ol><ul class="pager"><li class="current">Page 2 of 2</li></ul></body></html>
"""

BASE = "https://books.toscrape.com/catalogue/"


def test_parse_page_reads_every_field():
    rows, next_url = scraper.parse_page(PAGE_1, BASE + "page-1.html", "2026-01-01T00:00:00Z")
    assert len(rows) == 2
    first = rows[0]
    assert first["title"] == "A Light in the Attic"
    assert first["price_gbp"] == 51.77
    assert first["in_stock"] is True
    assert first["rating"] == 3
    assert first["url"] == BASE + "a-light-in-the-attic_1000/index.html"
    assert rows[1]["in_stock"] is False and rows[1]["rating"] == 1
    assert next_url == BASE + "page-2.html"


def test_last_page_has_no_next_link():
    _, next_url = scraper.parse_page(PAGE_2, BASE + "page-2.html", "t")
    assert next_url is None


def test_scrape_all_follows_pagination(monkeypatch):
    pages = {BASE + "page-1.html": PAGE_1, BASE + "page-2.html": PAGE_2}
    monkeypatch.setattr(scraper, "fetch", lambda session, url: pages[url])
    monkeypatch.setattr(scraper, "DELAY_SECONDS", 0)
    rows = scraper.scrape_all(BASE + "page-1.html")
    assert [r["title"] for r in rows] == ["A Light in the Attic", "Tipping the Velvet", "Soumission"]


def test_change_summary_spots_price_and_stock_moves():
    before = [{"url": "u1", "title": "Book A", "price_gbp": "10.00", "in_stock": "True"},
              {"url": "u2", "title": "Book B", "price_gbp": "20.00", "in_stock": "True"}]
    after = [{"url": "u1", "title": "Book A", "price_gbp": 12.5, "in_stock": True, "scraped_at": "t"},
             {"url": "u2", "title": "Book B", "price_gbp": 20.0, "in_stock": False, "scraped_at": "t"},
             {"url": "u3", "title": "Book C", "price_gbp": 5.0, "in_stock": True, "scraped_at": "t"}]
    report = scraper.summarize_changes(before, after)
    assert "£10.00 → £12.50" in report
    assert "Book B** now out of stock" in report
    assert "1 new item(s)" in report


def test_first_run_summary():
    report = scraper.summarize_changes([], [{"scraped_at": "t", "url": "u"}])
    assert "First run" in report
