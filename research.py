"""Daily worldwide research: select products using recent, verifiable cross-market sales evidence."""
import datetime, uuid
import requests
from common import gemini, extract_json, load_products, save_products

CATS = ["home", "beauty", "fashion", "gadgets", "pets", "fitness"]
PROFILE_LINK = "https://benable.com/MYCHOICE12"
today = datetime.date.today()
d = today.toordinal()
todays_cats = [CATS[(d * 3 + i) % len(CATS)] for i in range(3)]
products = load_products()
known = [p.get("title", "") for p in products]

prompt = f"""Today is {today.isoformat()}. Research products currently selling the MOST WORLDWIDE, across all major regions and countries.
Use live Google Search evidence, not guesses, old popularity, social-media hype alone, or generic evergreen recommendations.
Find 3 distinct physical products with global demand from these categories: {', '.join(todays_cats)}.
PRIORITY: products with the strongest recent sales evidence available (units sold, revenue, bestseller rank,
"bought in past month", or current marketplace sales ranking). Prefer evidence from the last 7-30 days and compare demand across countries/regions where possible.
Check Amazon Best Sellers and bought-in-past-month figures across major country marketplaces (Amazon US, UK, Canada, Germany, France, Italy, Spain, Japan, Australia, etc.); Walmart; eBay; Etsy; AliExpress; Temu; TikTok Shop across available countries; major regional retailers and marketplaces in Europe, Asia-Pacific, the Middle East, Latin America and other regions. Use the sources that provide accessible, credible, recent sales evidence. Do not limit research to the USA or to Amazon/Walmart. Do not claim an exact sales figure unless a source states it.
For each product include a concise sales_evidence field with the source name, date/window, and exact metric/rank
if available, plus a source_url to the specific product listing or sales evidence page.
Avoid products already used: {known}.
Only select products for which you can find a real product page AND a direct image URL for that exact product
from the same retailer/brand site. The image URL must point to an image file, not a search page.
Return ONLY a JSON array with up to 3 objects and keys:
"title", "category", "brand", "description" (factual, max 220 chars),
"why_trending" (one sentence tied to evidence), "sales_evidence", "source_url", "image_url".
Do not invent sales figures, sources, URLs, specifications, or image URLs. If evidence or exact product image
cannot be verified, omit that product. No markdown or extra text."""

items = extract_json(gemini(prompt, search=True, require_search=True))
if not isinstance(items, list):
    raise RuntimeError("Research returned no product list; products.json was not changed.")

new = []
seen = {x.strip().casefold() for x in known if x}
for it in items:
    if not isinstance(it, dict):
        continue
    required = ["title", "description", "source_url", "image_url", "sales_evidence"]
    if any(not str(it.get(k, "")).strip() for k in required):
        print("Skipping product missing sales evidence/source/image:", it.get("title", "unknown"))
        continue
    title_key = it["title"].strip().casefold()
    if title_key in seen:
        print("Skipping duplicate product:", it["title"])
        continue
    try:
        page = requests.get(it["source_url"], timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        page.raise_for_status()
        img = requests.get(it["image_url"], timeout=20, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        img.raise_for_status()
        if not img.headers.get("Content-Type", "").lower().startswith("image/"):
            raise ValueError("image URL did not return image content")
    except Exception as e:
        print("Skipping product with unverified URL:", it.get("title"), e)
        continue
    seen.add(title_key)
    new.append({
        "id": uuid.uuid4().hex[:8],
        "date": today.isoformat(),
        "title": it["title"],
        "category": it.get("category", ""),
        "brand": it.get("brand", ""),
        "description": it["description"],
        "why_trending": it.get("why_trending", ""),
        "sales_evidence": it["sales_evidence"],
        "source_url": it["source_url"],
        "image_url": it["image_url"],
        "benable_link": PROFILE_LINK,
        "posted_post": False,
        "posted_reel": False,
    })

if not new:
    raise RuntimeError("No products passed sales-evidence, source-page and exact-image checks. products.json unchanged.")

products.extend(new)
save_products(products)
with open("TODAY.md", "w", encoding="utf-8") as f:
    f.write(f"# Worldwide high-sales product research ({today.isoformat()})\\n\\n")
    f.write("In products ko Benable mein manually add karein. Selection recent sales evidence par based hai.\\n\\n")
    for p in new:
        f.write(f"## {p['title']}\\n- Category: {p['category']} | Brand: {p['brand']}\\n")
        f.write(f"- Sales evidence: {p['sales_evidence']}\\n- Description: {p['description']}\\n")
        f.write(f"- Product source: {p['source_url']}\\n- Exact product image: {p['image_url']}\\n\\n")
print("Added", len(new), "products with recent sales evidence and verified product image URLs.")
