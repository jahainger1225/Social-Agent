"""Import Amazon product links from the published Google Sheet.

Amazon product pages commonly block automated requests. This importer therefore
uses the ASIN with public search results for a title/description and never copies
Amazon images from scraped pages. Posts can use a text-only product graphic.
"""
import csv
import hashlib
import io
import re
from urllib.parse import urlparse, unquote
import requests
from ddgs import DDGS
from common import load_products, save_products

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSyr4NzhzaBKJ9eS7aoCa_Dq2ufkzvbsS5i5RSduiXU30WLWkSlxhnqKvIJ-femOcyCUUK9AJ3R2-kX/pub?gid=0&single=true&output=csv"
URL_RE = re.compile(r"https?://[^\\s,;]+", re.I)
ASIN_RE = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})", re.I)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SocialAgent/1.0)"}


def normalize_url(url):
    return url.rstrip(").]>\\\"' ")


def extract_asin(url):
    match = ASIN_RE.search(url)
    return match.group(1).upper() if match else ""


def lookup_product(url, asin):
    """Use public search snippets; do not scrape Amazon product advertising content."""
    queries = [f'"{asin}" Amazon product'] if asin else [url]
    for query in queries:
        try:
            results = DDGS().text(query, max_results=8)
            for result in results:
                result_url = result.get("href") or result.get("url") or ""
                title = (result.get("title") or "").strip()
                body = (result.get("body") or result.get("description") or "").strip()
                # Prefer an Amazon result that explicitly contains the same ASIN.
                if asin and "amazon.com" in result_url.lower() and asin.lower() not in result_url.lower():
                    continue
                if title and len(title) > 8 and "amazon.com" not in title.lower():
                    return title[:180], body[:450]
                if title and len(title) > 8:
                    return title[:180], body[:450]
        except Exception as exc:
            print("Search lookup warning:", str(exc)[:160])
    # A readable product slug is a useful fallback, but never invent a product name.
    path = unquote(urlparse(url).path)
    slug = re.sub(r"[-_]+", " ", path.split("/")[-1])
    slug = re.sub(r"\\?.*$", "", slug).strip()
    if slug and len(slug) > 8 and not re.fullmatch(r"[A-Z0-9]{10}", slug, re.I):
        return slug[:180].title(), "Product details are not available from public search yet."
    return "", ""


def main():
    response = requests.get(SHEET_CSV_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    rows = list(csv.reader(io.StringIO(response.text)))
    if not rows:
        raise RuntimeError("Google Sheet CSV is empty.")
    existing = load_products()
    seen = {p.get("sheet_url") or p.get("source_url") for p in existing}
    added = updated = skipped = 0
    processed = 0
    for row in rows:
        for cell in row:
            for raw_url in URL_RE.findall(cell or ""):
                url = normalize_url(raw_url)
                if "docs.google.com/spreadsheets" in url or "google.com" in url:
                    continue
                if url in seen:
                    continue
                seen.add(url)
                processed += 1
                asin = extract_asin(url)
                try:
                    title, description = lookup_product(url, asin)
                    if not title:
                        print("SKIP (no verifiable public title):", url)
                        skipped += 1
                        continue
                    pid = hashlib.sha1(url.encode()).hexdigest()[:8]
                    item = {
                        "id": pid,
                        "date": __import__("datetime").date.today().isoformat(),
                        "title": title,
                        "description": description,
                        "image_url": "",
                        "source_url": url,
                        "sheet_url": url,
                        "asin": asin,
                        "category": "shopping finds",
                        "brand": "",
                        "why_trending": "Product link supplied in the user's Google Sheet; trend status not independently verified.",
                        "posted_post": False,
                        "posted_reel": False,
                    }
                    existing.append(item)
                    added += 1
                    print("IMPORTED:", title, "| ASIN:", asin or "not found")
                except Exception as exc:
                    print("SKIP (lookup failed):", url, str(exc)[:180])
                    skipped += 1
    save_products(existing)
    print(f"Sheet import complete: {added} new products; {updated} updated; {skipped} skipped; {processed} new links checked.")
    if added == 0:
        print("No new products imported. Check search availability and the product URL format.")


if __name__ == "__main__":
    main()
