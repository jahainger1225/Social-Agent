import os, json, requests

MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"] if m]
PRODUCTS_FILE = "products.json"


def gemini(prompt, search=False):
    key = os.environ["GEMINI_API_KEY"]
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if search:
        body["tools"] = [{"google_search": {}}]
    last = None
    for model in MODELS:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json=body,
            timeout=180,
        )
        if r.status_code in (404, 400):
            print(f"Model {model} failed: {r.status_code} {r.text[:300]}")
            last = r
            continue
        r.raise_for_status()
        print("Using model:", model)
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    last.raise_for_status()


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
