import os, json, requests

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
PRODUCTS_FILE = "products.json"


def gemini(prompt, search=False):
    key = os.environ["GEMINI_API_KEY"]
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if search:
        body["tools"] = [{"google_search": {}}]
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        headers={"x-goog-api-key": key},
        json=body,
        timeout=180,
    )
    r.raise_for_status()
    parts = r.json()["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def extract_json(text):
    t = text.strip()
    starts = [i for i in (t.find("["), t.find("{")) if i != -1]
    s = min(starts)
    e = max(t.rfind("]"), t.rfind("}"))
    return json.loads(t[s : e + 1])


def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        return []
    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=2, ensure_ascii=False)
