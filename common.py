import os, json, time, requests

MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash"] if m]
PRODUCTS_FILE = "products.json"


def _call(model, body):
    key = os.environ["GEMINI_API_KEY"]
    return requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key},
        json=body,
        timeout=180,
    )


def gemini(prompt, search=False):
    modes = [True, False] if search else [False]
    for use_search in modes:
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        if use_search:
            body["tools"] = [{"google_search": {}}]
        elif search:
            print("WARNING: web search nahi chala, bina search ke koshish ho rahi hai.")
        for model in MODELS:
            for attempt in range(2):
                r = _call(model, body)
                if r.status_code == 429 and attempt == 0:
                    print(f"{model} (search={use_search}) 429: {r.text[:400]}")
                    time.sleep(30)
                    continue
                break
            if r.ok:
                print("Using model:", model, "search:", use_search)
                parts = r.json()["candidates"][0]["content"]["parts"]
                return "".join(p.get("text", "") for p in parts)
            print(f"{model} (search={use_search}) failed {r.status_code}: {r.text[:400]}")
    raise RuntimeError("Sab Gemini models fail ho gaye. Upar ke logs dekhein.")


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
