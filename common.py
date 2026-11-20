import os, json, time, requests

MODELS = [m for m in [os.getenv("GEMINI_MODEL"), "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-3.5-flash-lite"] if m]
PRODUCTS_FILE = "products.json"
NO_SEARCH_NOTE = (
    "\n\nNOTE: web search is unavailable right now. Pick only well-known, established "
    "best-selling products from major brands that you are confident exist. Do not invent "
    "specifications or claim live sales data."
)


def _call(model, body):
    key = os.environ["GEMINI_API_KEY"]
    try:
        return requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": key},
            json=body,
            timeout=90,
        )
    except requests.RequestException as e:
        print(f"{model}: network error {type(e).__name__}")
        return None


def _try(prompt, search, models, rounds=1):
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if search:
        body["tools"] = [{"google_search": {}}]
    for rnd in range(rounds):
        for model in models:
            for attempt in range(2):
                r = _call(model, body)
                if r is not None and r.ok:
                    parts = r.json()["candidates"][0]["content"]["parts"]
                    print("Using model:", model, "| search:", search)
                    return "".join(p.get("text", "") for p in parts)
                code = r.status_code if r is not None else "timeout"
                print(f"{model} (search={search}) failed: {code} {r.text[:200] if r is not None else ''}")
                if code in (429, 500, 503, "timeout") and attempt == 0:
                    time.sleep(20)
                    continue
                break
        if rnd < rounds - 1:
            time.sleep(45)
    return None


def gemini(prompt, search=False, require_search=False):
    if search:
        text = _try(prompt, True, MODELS, rounds=1)
        if text:
            return text
        if require_search:
            raise RuntimeError("Live Google Search unavailable. Strict research stopped; no unverified products will be added.")
        print("WARNING: web search nahi chala, bina search ke aage barh rahe hain.")
        prompt += NO_SEARCH_NOTE
    text = _try(prompt, False, MODELS, rounds=2)
    if text:
        return text
    raise RuntimeError("Sab Gemini models fail ho gaye. Upar ke logs dekhein, thori der baad dobara chalayein.")


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
