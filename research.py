"""Free product discovery using public search endpoints (no Gemini/API key).

Search results are discovery leads, not audited sales data. A product is only
accepted when the result contains a clear bestseller/sold signal and its own
page exposes title, description and a valid product image.
"""
import datetime
import json
import re
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from common import load_products, save_products

PROFILE_LINK = "https://benable.com/MYCHOICE12"
CATEGORIES = {
    "home": ["home products bestseller sold", "home best sellers bought in past month"],
    "beauty": ["beauty skincare bestseller sold", "beauty best sellers bought in past month"],
    "fashion": ["fashion accessories bestseller sold", "fashion best sellers bought in past month"],
    "gadgets": ["electronics gadgets bestseller sold", "tech gadgets best sellers bought in past month"],
    "pets": ["pet supplies bestseller sold", "pet products best sellers bought in past month"],
    "fitness": ["fitness equipment bestseller sold", "fitness products best sellers bought in past month"],
}
MARKETPLACES = [
    "Amazon", "Walmart", "eBay", "Etsy", "AliExpress", "Temu", "TikTok Shop"
]
REGIONS = ["United States", "United Kingdom", "Canada", "Germany", "Japan", "Australia", "India"]

TODAY = datetime.date.today()
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

SALES_SIGNAL = re.compile(
    r"(\b[\d,.]+\s*(?:k\+?\s*)?(?:sold|purchased)\b|"
    r"\b(?:best\s*seller|bestseller|best-selling|top\s*selling)\b|"
    r"\b(?:bought|purchased)\s+in\s+past\s+month\b)",
    re.I,
)


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def search_bing_rss(query):
    """Bing's public RSS search endpoint; no key required."""
    url = "https://www.bing.com/search"
    response = SESSION.get(url, params={"format": "rss", "q": query}, timeout=12)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    rows = []
    for item in root.findall(".//item"):
        rows.append({
            "title": clean(item.findtext("title")),
            "body": clean(item.findtext("description")),
            "href": clean(item.findtext("link")),
            "engine": "Bing RSS",
        })
    return rows


def search_ddg(query):
    """DuckDuckGo is a secondary public search source."""
    rows = []
    with DDGS() as ddgs:
        for item in ddgs.text(query, max_results=8, safesearch="moderate"):
            rows.append({
                "title": clean(item.get("title")),
                "body": clean(item.get("body")),
                "href": clean(item.get("href") or item.get("url")),
                "engine": "DuckDuckGo",
            })
    return rows


def search_web(query):
    errors = []
    for engine in (search_bing_rss, search_ddg):
        try:
            rows = engine(query)
            if rows:
                print(f"{engine.__name__}: {len(rows)} results")
                return rows
            errors.append(f"{engine.__name__}: no results")
        except Exception as exc:
            errors.append(f"{engine.__name__}: {type(exc).__name__}: {str(exc)[:180]}")
            print(errors[-1])
    print("All free search sources unavailable for this query.")
    return []


def page_metadata(soup, keys):
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def inspect_product(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    host = parsed.netloc.lower()
    if any(x in host for x in ("bing.com", "duckduckgo.com", "google.com", "yahoo.com")):
        return None
    try:
        response = SESSION.get(url, timeout=10, allow_redirects=True)
        response.raise_for_status()
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return None
        soup = BeautifulSoup(response.text[:2_000_000], "html.parser")
        title = page_metadata(soup, ["og:title", "twitter:title"])
        if not title and soup.title:
            title = clean(soup.title.get_text(" ", strip=True))
        description = page_metadata(soup, ["og:description", "description", "twitter:description"])
        image = page_metadata(soup, ["og:image", "twitter:image"])
        if not title or not description or not image:
            return None
        if image.startswith("//"):
            image = "https:" + image
        if image.startswith("/"):
            image = response.url.rstrip("/") + image
        image_response = SESSION.get(image, timeout=8, stream=True, allow_redirects=True)
        image_response.raise_for_status()
        if not image_response.headers.get("Content-Type", "").lower().startswith("image/"):
            return None
        return {
            "title": title[:180],
            "description": description[:220],
            "image_url": image_response.url,
            "source_url": response.url,
        }
    except Exception as exc:
        print("Product page skipped:", url[:160], type(exc).__name__)
        return None


def discover(category, query, seen):
    """One broad search per category; keep the daily run bounded and predictable."""
    marketplace_terms = "Amazon OR Walmart OR eBay OR Etsy OR AliExpress OR Temu OR TikTok Shop"
    region_terms = " OR ".join(REGIONS)
    q = f'{query} ({marketplace_terms}) ({region_terms})'
    results = search_web(q)
    found = []
    inspected = 0

    for row in results:
        href = row.get("href", "")
        evidence = clean(row.get("title", "") + " " + row.get("body", ""))
        if not href or not SALES_SIGNAL.search(evidence):
            continue
        inspected += 1
        if inspected > 6:
            break
        product = inspect_product(href)
        if not product:
            continue
        key = product["title"].casefold()
        if key in seen:
            continue
        product.update({
            "category": category,
            "brand": "",
            "sales_evidence": (
                f'{row.get("engine")} public search result, {TODAY.isoformat()}: '
                f'{evidence[:300]}. Search-result signal only; not independently audited sales volume.'
            ),
            "why_trending": "A public search result showed a bestseller or sold-count phrase; actual sales volume was not independently verified.",
        })
        seen.add(key)
        found.append(product)
        if len(found) >= 2:
            break
    return found

def main():
    products = load_products()
    seen = {clean(p.get("title", "")).casefold() for p in products if p.get("title")}
    category_names = list(CATEGORIES)
    # Rotate category order daily so every category gets a fair chance.
    offset = TODAY.toordinal() % len(category_names)
    category_names = category_names[offset:] + category_names[:offset]
    new_products = []

    for category in category_names:
        # Use one query per category instead of hundreds of marketplace/region requests.
        query = CATEGORIES[category][0]
        new_products.extend(discover(category, query, seen))
        if len(new_products) >= 3:
            break

    with open("TODAY.md", "w", encoding="utf-8") as f:
        f.write(f"# Worldwide product discovery ({TODAY.isoformat()})\n\n")
        f.write("Free public search; sales signals are not independently audited. Add products to Benable manually.\n\n")
        if not new_products:
            f.write("No products passed the sales-signal, product-page and exact-image checks today. No unverified products were added.\n")
        for p in new_products:
            p.update({
                "id": uuid.uuid4().hex[:8],
                "date": TODAY.isoformat(),
                "benable_link": PROFILE_LINK,
                "posted_post": False,
                "posted_reel": False,
            })
            f.write(f"## {p['title']}\n")
            f.write(f"- Category: {p['category']}\n- Description: {p['description']}\n")
            f.write(f"- Sales signal: {p['sales_evidence']}\n")
            f.write(f"- Product page: {p['source_url']}\n- Exact product image: {p['image_url']}\n\n")

    if new_products:
        products.extend(new_products)
        save_products(products)
        print(f"Added {len(new_products)} verified-page product(s) using free public search.")
    else:
        print("Research completed: zero qualifying products today. Existing products unchanged; see TODAY.md.")
    print("Research workflow finished without paid API dependencies.")


if __name__ == "__main__":
    main()
