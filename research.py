"""Free worldwide product discovery using public DuckDuckGo search results.

This does not use Gemini or any paid API. Search snippets are treated as evidence
only when they explicitly mention a sales/ranking signal. Product pages must expose
their own title, description and image metadata before they are accepted.
"""
import datetime
import json
import re
import time
import uuid
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from common import load_products, save_products

PROFILE_LINK = "https://benable.com/MYCHOICE12"
CATEGORIES = {
    "home": ["home best sellers products bought in past month", "home products best selling products sold"],
    "beauty": ["beauty best sellers products bought in past month", "skincare makeup best selling products"],
    "fashion": ["fashion accessories best sellers bought in past month", "fashion products best selling sold"],
    "gadgets": ["electronics gadgets best sellers bought in past month", "popular tech gadgets best selling products"],
    "pets": ["pet supplies best sellers bought in past month", "pet products best selling sold"],
    "fitness": ["fitness equipment best sellers bought in past month", "fitness products best selling sold"],
}
MARKETPLACES = [
    "Amazon US", "Amazon UK", "Amazon Canada", "Amazon Germany",
    "Amazon Japan", "Walmart", "eBay", "Etsy", "AliExpress",
    "Temu", "TikTok Shop",
]
REGIONS = ["United States", "United Kingdom", "Canada", "Germany", "Japan", "Australia", "India"]

TODAY = datetime.date.today()
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ProductResearchBot/1.0)"}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)

# A result is eligible only if its own text states a sales or bestseller signal.
SALES_SIGNAL = re.compile(
    r"(\b[\d,.]+\s*(?:k\\+?\s*)?(?:sold|purchased)\b|"
    r"\b(?:best\s*seller|bestseller|best-selling|top\s*selling)\b|"
    r"\b(?:bought|purchased)\s+in\s+past\s+month\b|"
    r"\b\d[\d,]*\s+reviews?\b)",
    re.I,
)


def clean(value):
    return re.sub(r"\s+", " ", value or "").strip()


def metadata(soup, *keys):
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def inspect_product(url):
    """Read the exact product page; return its own metadata and a verified image URL."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    try:
        response = SESSION.get(url, timeout=18, allow_redirects=True)
        response.raise_for_status()
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return None
        soup = BeautifulSoup(response.text[:2_000_000], "html.parser")
        title = metadata(soup, "og:title", "twitter:title")
        if not title and soup.title:
            title = clean(soup.title.get_text(" ", strip=True))
        description = metadata(soup, "og:description", "description", "twitter:description")
        image = metadata(soup, "og:image", "twitter:image")
        if not title or not description or not image:
            return None
        image_response = SESSION.get(image, timeout=18, stream=True, allow_redirects=True)
        image_response.raise_for_status()
        content_type = image_response.headers.get("Content-Type", "").lower()
        if not content_type.startswith("image/"):
            return None
        return {
            "title": title[:180],
            "description": description[:220],
            "image_url": image_response.url,
            "source_url": response.url,
        }
    except Exception as exc:
        print("Page/image verification skipped:", url, type(exc).__name__)
        return None


def search_candidates(category, query, seen):
    found = []
    for region in REGIONS:
        q = f"{query} {region} " + " ".join(MARKETPLACES)
        try:
            with DDGS() as ddgs:
                results = ddgs.text(q, max_results=8, safesearch="moderate")
                for result in results:
                    href = result.get("href") or result.get("url") or ""
                    snippet = clean(result.get("body", ""))
                    heading = clean(result.get("title", ""))
                    evidence_text = clean(heading + " " + snippet)
                    if not href or not SALES_SIGNAL.search(evidence_text):
                        continue
                    host = urlparse(href).netloc.lower()
                    if not host or any(x in host for x in ("duckduckgo.com", "google.com", "bing.com")):
                        continue
                    candidate = inspect_product(href)
                    if not candidate:
                        continue
                    key = candidate["title"].casefold()
                    if key in seen:
                        continue
                    candidate.update({
                        "category": category,
                        "brand": "",
                        "sales_evidence": (
                            f"Public search result retrieved {TODAY.isoformat()}; "
                            f"listing/search text: {evidence_text[:350]}. "
                            "This is a search-result signal, not independently audited sales data."
                        ),
                        "why_trending": "Public marketplace/search listing displayed a bestseller or sales-related signal; exact sales volume was not independently verified.",
                    })
                    found.append(candidate)
                    seen.add(key)
                    if len(found) >= 2:
                        return found
            time.sleep(1.5)
        except Exception as exc:
            print("Search temporarily unavailable:", region, type(exc).__name__)
            time.sleep(3)
    return found


def main():
    products = load_products()
    seen = {clean(p.get("title", "")).casefold() for p in products if p.get("title")}
    day_index = TODAY.toordinal()
    categories = list(CATEGORIES)
    start = day_index % len(categories)
    categories = categories[start:] + categories[:start]
    new_products = []

    for category in categories:
        for query in CATEGORIES[category]:
            candidates = search_candidates(category, query, seen)
            for item in candidates:
                item.update({
                    "id": uuid.uuid4().hex[:8],
                    "date": TODAY.isoformat(),
                    "benable_link": PROFILE_LINK,
                    "posted_post": False,
                    "posted_reel": False,
                })
                new_products.append(item)
                if len(new_products) >= 3:
                    break
            if len(new_products) >= 3:
                break
        if len(new_products) >= 3:
            break

    if not new_products:
        raise RuntimeError(
            "Free search did not find any product with both a sales-related listing signal "
            "and a verified product-page image. Existing products were left unchanged."
        )

    products.extend(new_products)
    save_products(products)
    with open("TODAY.md", "w", encoding="utf-8") as f:
        f.write(f"# Worldwide product discovery ({TODAY.isoformat()})\n\n")
        f.write("Free public search. Sales signals are not independently audited. Add products to Benable manually.\n\n")
        for p in new_products:
            f.write(f"## {p['title']}\n")
            f.write(f"- Category: {p['category']}\n- Description: {p['description']}\n")
            f.write(f"- Sales signal: {p['sales_evidence']}\n")
            f.write(f"- Product page: {p['source_url']}\n- Exact product image: {p['image_url']}\n\n")
    print(f"Added {len(new_products)} product(s) using free public search.")


if __name__ == "__main__":
    main()
