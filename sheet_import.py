"""Import product URLs from the public Google Sheet CSV into products.json.

The sheet is read-only. Existing post/reel status is preserved by source URL.
"""
import csv
import hashlib
import io
import os
import re
import requests
from bs4 import BeautifulSoup
from common import load_products, save_products

SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSyr4NzhzaBKJ9eS7aoCa_Dq2ufkzvbsS5i5RSduiXU30WLWkSlxhnqKvIJ-femOcyCUUK9AJ3R2-kX/pub?gid=0&single=true&output=csv"
URL_RE = re.compile(r"https?://[^\s,;]+", re.I)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SocialAgent/1.0)"}

def product_details(url):
    response = requests.get(url, headers=HEADERS, timeout=25, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    def meta(*keys):
        for key in keys:
            tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""
    title = meta("og:title", "twitter:title")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    image = meta("og:image", "twitter:image")
    description = meta("og:description", "description", "twitter:description")
    return {
        "title": title[:180],
        "image_url": image,
        "description": description[:500],
        "source_url": response.url,
    }

def main():
    response = requests.get(SHEET_CSV_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    rows = list(csv.reader(io.StringIO(response.text)))
    if not rows:
        raise RuntimeError("Google Sheet CSV is empty.")
    existing = load_products()
    by_url = {p.get("source_url"): p for p in existing if p.get("source_url")}
    seen = set(by_url)
    added = updated = skipped = 0
    for row in rows:
        for cell in row:
            for url in URL_RE.findall(cell or ""):
                url = url.rstrip(").]}>")
                if "docs.google.com/spreadsheets" in url or "google.com" in url:
                    continue
                if url in seen:
                    continue
                seen.add(url)
                try:
                    details = product_details(url)
                    if not details["title"] or not details["image_url"]:
                        print("SKIP (missing title/image):", url)
                        skipped += 1
                        continue
                    pid = hashlib.sha1(url.encode()).hexdigest()[:8]
                    item = {
                        "id": pid,
                        "date": __import__("datetime").date.today().isoformat(),
                        **details,
                        "category": "shopping finds",
                        "brand": "",
                        "why_trending": "Product link supplied in the user's Google Sheet.",
                        "sheet_url": url,
                        "posted_post": False,
                        "posted_reel": False,
                    }
                    existing.append(item)
                    added += 1
                    print("IMPORTED:", item["title"])
                except Exception as exc:
                    print("SKIP (page could not be read):", url, str(exc)[:180])
                    skipped += 1
    save_products(existing)
    print(f"Sheet import complete: {added} new products; {updated} updated; {skipped} skipped.")
    if added == 0:
        print("No new eligible products were imported. Check that the published sheet contains product URLs and that product pages expose a public image.")

if __name__ == "__main__":
    main()
