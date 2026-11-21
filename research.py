"""Amazon US deal discovery: accept only product pages with verifiable 30%+ discounts.

Free public search is used for discovery. Amazon may block automated page access;
blocked or incomplete pages are skipped rather than guessed. No paid API is used.
"""
import datetime
import json
import re
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from common import load_products, save_products

PROFILE_LINK = "https://benable.com/MYCHOICE12"
TODAY = datetime.date.today()
MIN_DISCOUNT = 30
MAX_RESULTS = 10
CATEGORIES = {
    "home": ["home deals", "kitchen deals", "vacuum deals"],
    "beauty": ["beauty deals", "skincare deals", "hair care deals"],
    "fashion": ["fashion deals", "shoes deals", "bags deals"],
    "gadgets": ["electronics deals", "headphones deals", "smart home deals"],
    "pets": ["pet supplies deals", "dog products deals"],
    "fitness": ["fitness equipment deals", "fitness tracker deals"],
}
DISCOUNT_TIERS = (55, 50, 40, 30)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def amazon_product_url(url):
    try:
        p = urlparse(url)
        host = p.netloc.lower().split(":")[0]
        if host not in ("amazon.com", "www.amazon.com", "smile.amazon.com"):
            return ""
        match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})", p.path, re.I)
        if not match:
            return ""
        return f"https://www.amazon.com/dp/{match.group(1).upper()}"
    except Exception:
        return ""


def search_bing(query):
    r = SESSION.get("https://www.bing.com/search",
                    params={"format": "rss", "q": query}, timeout=15)
    r.raise_for_status()
    root = ET.fromstring(r.text)
    return [{"title": clean(x.findtext("title")),
             "body": clean(x.findtext("description")),
             "href": clean(x.findtext("link"))} for x in root.findall(".//item")]


def search_ddg(query):
    with DDGS() as ddgs:
        return [{"title": clean(x.get("title")), "body": clean(x.get("body")),
                 "href": clean(x.get("href") or x.get("url"))}
                for x in ddgs.text(query, max_results=10, safesearch="moderate")]


def search_web(query):
    for engine in (search_bing, search_ddg):
        try:
            rows = engine(query)
            print(f"{engine.__name__}: {len(rows)} results")
            if rows:
                return rows
        except Exception as exc:
            print(f"{engine.__name__} failed: {type(exc).__name__}: {str(exc)[:160]}")
    return []


def meta(soup, *keys):
    for key in keys:
        tag = soup.find("meta", attrs={"property": key}) or soup.find("meta", attrs={"name": key})
        if tag and tag.get("content"):
            return clean(tag["content"])
    return ""


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk_json(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_json(v)


def price_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"(?:US\s*\$|\$)\s*([\d,]+(?:\.\d{1,2})?)", str(value))
    if not m:
        m = re.search(r"([\d,]+\.\d{2})", str(value))
    return float(m.group(1).replace(",", "")) if m else None


def extract_prices(soup):
    current = old = None
    currency = "USD"
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text())
        except Exception:
            continue
        for obj in walk_json(data):
            if str(obj.get("@type", "")).lower() in ("product", "offer", "aggregateoffer"):
                offers = obj.get("offers", obj)
                offer_list = offers if isinstance(offers, list) else [offers]
                for offer in offer_list:
                    if not isinstance(offer, dict):
                        continue
                    cur = price_number(offer.get("price") or offer.get("lowPrice"))
                    if cur and current is None:
                        current = cur
                    currency = offer.get("priceCurrency") or currency
    # Amazon's visible price blocks. These are only accepted when both values exist.
    text = soup.get_text(" ", strip=True)
    if current is None:
        for selector in ("span.a-price span.a-offscreen", "#priceblock_dealprice",
                         "#priceblock_ourprice", "#corePrice_feature_div"):
            node = soup.select_one(selector)
            if node:
                current = price_number(node.get_text(" ", strip=True))
                if current:
                    break
    for selector in ("span.a-text-price span.a-offscreen", "#priceblock_listprice",
                     "#listPrice"):
        node = soup.select_one(selector)
        if node:
            old = price_number(node.get_text(" ", strip=True))
            if old:
                break
    if old is None:
        m = re.search(r"(?:List Price|Typical price|Was)\s*:?\s*(US\s*\$|\$)\s*([\d,]+\.\d{2})", text, re.I)
        if m:
            old = float(m.group(2).replace(",", ""))
    if current is None:
        # Fallback to an explicit current-price label only, never an arbitrary page number.
        m = re.search(r"(?:Deal Price|Price)\s*:?\s*(US\s*\$|\$)\s*([\d,]+\.\d{2})", text, re.I)
        if m:
            current = float(m.group(2).replace(",", ""))
    return current, old, currency


def inspect_product(url):
    try:
        response = SESSION.get(url, timeout=18, allow_redirects=True)
        response.raise_for_status()
        if "text/html" not in response.headers.get("Content-Type", "").lower():
            return None
        soup = BeautifulSoup(response.text[:3_000_000], "html.parser")
        title = meta(soup, "og:title", "twitter:title")
        if not title and soup.title:
            title = clean(soup.title.get_text(" ", strip=True))
        description = meta(soup, "og:description", "description")
        image = meta(soup, "og:image", "twitter:image")
        current, old, currency = extract_prices(soup)
        if not title or not image or not current or not old or old <= current or currency != "USD":
            print("Skipped: missing verifiable title/image/current+list price", url)
            return None
        discount = round((old - current) / old * 100)
        if discount < MIN_DISCOUNT:
            print(f"Skipped: verified discount only {discount}%", url)
            return None
        if image.startswith("//"):
            image = "https:" + image
        img = SESSION.get(image, timeout=12, stream=True)
        img.raise_for_status()
        if not img.headers.get("Content-Type", "").lower().startswith("image/"):
            return None
        return {
            "title": title[:180],
            "description": (description or title)[:240],
            "image_url": img.url,
            "source_url": amazon_product_url(response.url),
            "sale_price": round(current, 2),
            "original_price": round(old, 2),
            "currency": "USD",
            "discount_percent": discount,
        }
    except Exception as exc:
        print("Product page unavailable:", url[:140], type(exc).__name__, str(exc)[:120])
        return None


def main():
    products = load_products()
    seen = {clean(p.get("title")).casefold() for p in products if p.get("title")}
    new_products = []
    candidates_seen = set()

    # Search broad Amazon deal language: sellers use both "% off" and "Save X%".
    # One query per category keeps the free workflow within reasonable limits.
    for category, terms in CATEGORIES.items():
        term = terms[0]
        query = (
            f'site:amazon.com ("30% off" OR "40% off" OR "50% off" OR '
            f'"55% off" OR "Save 30%" OR "Save 40%" OR "Save 50%") {term}'
        )
        rows = search_web(query)
        print(f"Category {category}: {len(rows)} search candidates")
        inspected = 0
        for row in rows:
            evidence = clean(row.get("title", "") + " " + row.get("body", ""))
            if not re.search(r"(?:30|40|50|55)\s*%\s*off|save\s+(?:30|40|50|55)\s*%", evidence, re.I):
                continue
            href = amazon_product_url(row.get("href", ""))
            if not href or href in candidates_seen:
                continue
            candidates_seen.add(href)
            inspected += 1
            if inspected > 5:
                break
            product = inspect_product(href)
            if not product:
                continue
            key = product["title"].casefold()
            if key in seen:
                continue
            product.update({
                "id": uuid.uuid4().hex[:8],
                "date": TODAY.isoformat(),
                "category": category,
                "brand": "",
                "benable_link": PROFILE_LINK,
                "posted_post": False,
                "posted_reel": False,
                "why_trending": f"Amazon US product page showed a verified {product['discount_percent']}% reduction from listed price. Discount is a deal signal, not proof of sales volume.",
                "deal_source": "Amazon US product page; prices and discount checked during discovery.",
            })
            seen.add(key)
            new_products.append(product)
            if len(new_products) >= MAX_RESULTS:
                break
        if len(new_products) >= MAX_RESULTS:
            break

    with open("TODAY.md", "w", encoding="utf-8") as f:
        f.write(f"# Amazon US deals ({TODAY.isoformat()})\n\n")
        f.write(f"Free public search. Only product pages with a verified discount of {MIN_DISCOUNT}% or more are included. Prices may change; check Amazon before sharing.\n\n")
        if not new_products:
            f.write("No product passed the Amazon page, image and price verification checks today. Search candidates are not treated as confirmed deals.\n")
        for p in new_products:
            f.write(f"## {p['title']}\n")
            f.write(f"- Category: {p['category']}\n- Discount: {p['discount_percent']}% off\n")
            f.write(f"- Original price: ${p['original_price']:.2f} {p['currency']}\n")
            f.write(f"- Deal price: ${p['sale_price']:.2f} {p['currency']}\n")
            f.write(f"- Product page: {p['source_url']}\n- Exact image: {p['image_url']}\n\n")

    if new_products:
        products.extend(new_products)
        save_products(products)
    print(f"Amazon deal research finished: {len(new_products)} verified deal(s).")
    print("No paid API dependencies. Products were not published automatically.")


if __name__ == "__main__":
    main()
