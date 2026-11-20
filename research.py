"""Daily: find 3 trending products and add them to products.json."""
import datetime, uuid
from common import gemini, extract_json, load_products, save_products

CATS = ["home", "beauty", "fashion", "gadgets", "pets", "fitness"]
today = datetime.date.today()
d = today.toordinal()
todays_cats = [CATS[(d * 3 + i) % len(CATS)] for i in range(3)]

products = load_products()
known = [p.get("title", "") for p in products]

prompt = f"""Today is {today.isoformat()}. Use Google Search to find 3 products that are
trending or selling very well right now with shoppers in the USA, UK, Canada, Australia and
New Zealand. One product for each of these categories: {', '.join(todays_cats)}.
Prefer products that are widely available from well known brands/retailers, and consider
seasonal gift demand. Do not pick any of these already used: {known}.

Return ONLY a JSON array of 3 objects with keys:
"title" (product name, max 70 chars),
"category",
"description" (max 220 chars, factual, ONLY facts you found; do not invent specs),
"why_trending" (one sentence),
"brand".
No markdown, no extra text."""

items = extract_json(gemini(prompt, search=True))
if not isinstance(items, list) or not items:
    raise RuntimeError("Research returned no product list; products.json was not changed.")
new = []
seen = {x.strip().casefold() for x in known if x}
for it in items:
    if not isinstance(it, dict) or not it.get("title") or not it.get("description"):
        print("Skipping incomplete research result:", it)
        continue
    title_key = it["title"].strip().casefold()
    if title_key in seen:
        print("Skipping duplicate product:", it["title"])
        continue
    seen.add(title_key)
    new.append(
        {
            "id": uuid.uuid4().hex[:8],
            "date": today.isoformat(),
            "title": it["title"],
            "category": it.get("category", ""),
            "brand": it.get("brand", ""),
            "description": it.get("description", ""),
            "why_trending": it.get("why_trending", ""),
            "image_url": "",
            "benable_link": "",
            "posted_post": False,
            "posted_reel": False,
        }
    )
if not new:
    raise RuntimeError("Research found no new complete products; products.json was not changed.")
products.extend(new)
save_products(products)

with open("TODAY.md", "w", encoding="utf-8") as f:
    f.write(f"# Aaj ke products ({today.isoformat()})\n\n")
    f.write("Har product ko Benable mein add karein, phir products.json mein uske saamne\n")
    f.write('`"benable_link": ""` ke andar apna Benable link paste karein.\n')
    f.write('(Optional) `"image_url"` mein product ki official image ka link daal sakte hain.\n\n')
    for p in new:
        f.write(f"## {p['title']}\n- Category: {p['category']} | Brand: {p['brand']}\n")
        f.write(f"- Description: {p['description']}\n- Kyun trending: {p['why_trending']}\n- id: {p['id']}\n\n")
print("Added", len(new), "products")
