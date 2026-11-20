"""Usage: python post.py post|reel
Picks the first product that has a benable_link and has not been posted in this format,
writes the copy with Gemini, builds the media, publishes to Instagram + Facebook Page."""
import os, sys, io, json, time, shutil, random, subprocess
import requests
from PIL import Image, ImageDraw, ImageFont
from common import gemini, extract_json, load_products, save_products

KIND = sys.argv[1] if len(sys.argv) > 1 else "post"
DRY = os.getenv("DRY_RUN", "0") == "1"
TOKEN = os.getenv("META_TOKEN")
IG = os.getenv("IG_USER_ID")
PAGE = os.getenv("FB_PAGE_ID")
GRAPH = f"https://graph.facebook.com/{os.getenv('GRAPH_VERSION', 'v23.0')}"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
DISCLOSURE = "Affiliate disclosure: this post contains affiliate links and I may earn a small commission at no extra cost to you."


def default_link():
    """Benable profile fallback; product-specific Benable links take priority."""
    profile = "https://benable.com/MYCHOICE12"
    try:
        with open("config.json", encoding="utf-8") as f:
            return json.load(f).get("default_link", "").strip() or profile
    except Exception:
        return profile


def git(*a):
    subprocess.run(["git", *a], check=True)


# ---------- copywriting ----------
def make_copy(p):
    prompt = f"""Write social media copy for this product. Audience: USA, UK, Canada, Australia, NZ.
Product: {p['title']}
Facts (use ONLY these, do not invent features or claims): {p['description']}

Return ONLY JSON: {{"hook": "max 8 words, scroll-stopping",
"caption": "2-3 short lines in friendly American English, 2-3 emojis, ends with a call to action",
"hashtags": ["8 to 10 relevant hashtags without the # sign"]}}
Rules: no medical or income claims, no fake urgency or fake discounts, no 'best in the world'."""
    return extract_json(gemini(prompt))


def captions(p, c, link):
    tags = " ".join("#" + t.strip("# ").replace(" ", "") for t in c["hashtags"][:10])
    ig = f"{c['caption']}\n\nLink in bio\n\n{DISCLOSURE}\n\n{tags} #affiliate"
    fb = f"{c['caption']}\n\nGet it here: {link}\n\n{DISCLOSURE}\n\n{tags} #affiliate"
    return ig, fb


# ---------- images ----------
def fetch_image(url):
    try:
        r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print("Image download failed, using text card:", e)
        return None


def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    img = img.resize((int(img.width * s) + 1, int(img.height * s) + 1))
    x, y = (img.width - w) // 2, (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def gradient(w, h, seed):
    random.seed(seed)
    c1 = tuple(random.randint(20, 110) for _ in range(3))
    c2 = tuple(random.randint(90, 200) for _ in range(3))
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        px.line([(0, y), (w, y)], fill=tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)))
    return img


def wrap(d, text, font, max_w):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if d.textlength(trial, font=font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def render(w, h, bg, text, size, pos="bottom", footer=None):
    base = (cover(bg, w, h) if bg else gradient(w, h, text)).convert("RGBA")
    font = ImageFont.truetype(FONT, size)
    d = ImageDraw.Draw(base)
    lines = wrap(d, text, font, int(w * 0.84))
    lh = int(size * 1.25)
    th = lh * len(lines)
    y0 = h - th - int(h * 0.12) if pos == "bottom" else (h - th) // 2
    band = Image.new("RGBA", base.size, (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle([0, y0 - 30, w, y0 + th + 30], fill=(0, 0, 0, 150))
    base = Image.alpha_composite(base, band)
    d = ImageDraw.Draw(base)
    for i, line in enumerate(lines):
        d.text(((w - d.textlength(line, font=font)) / 2, y0 + i * lh), line, font=font, fill="white")
    if footer:
        f2 = ImageFont.truetype(FONT, 32)
        d.text(((w - d.textlength(footer, font=f2)) / 2, h - 70), footer, font=f2, fill="white")
    return base.convert("RGB")


def build_media(p, c):
    os.makedirs("out", exist_ok=True)
    bg = fetch_image(p["image_url"]) if p.get("image_url") else None
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if KIND == "post":
        img = render(1080, 1350, bg, p["title"], 64, "bottom", footer="Link in bio | Affiliate")
        path = f"out/post-{stamp}.jpg"
        img.save(path, quality=92)
        return path
    frames = [
        render(1080, 1920, None, c["hook"], 84, "center"),
        render(1080, 1920, bg, p["title"], 70, "bottom"),
        render(1080, 1920, None, "Link in bio", 90, "center", footer="Affiliate link. I may earn a commission."),
    ]
    for i, f in enumerate(frames):
        f.save(f"out/f{i}.png")
    path = f"out/reel-{stamp}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-loop", "1", "-t", "4", "-i", "out/f0.png",
         "-loop", "1", "-t", "5", "-i", "out/f1.png",
         "-loop", "1", "-t", "4", "-i", "out/f2.png",
         "-f", "lavfi", "-t", "13", "-i", "anullsrc=r=44100:cl=stereo",
         "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0,fps=30,format=yuv420p[v]",
         "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-c:a", "aac", "-shortest",
         "-movflags", "+faststart", path],
        check=True,
    )
    return path


# ---------- hosting + publishing ----------
def host(path):
    os.makedirs("media", exist_ok=True)
    dest = f"media/{os.path.basename(path)}"
    shutil.copy(path, dest)
    git("add", dest)
    git("commit", "-m", f"media {dest}")
    git("pull", "--rebase")
    git("push")
    url = f"https://raw.githubusercontent.com/{os.environ['GITHUB_REPOSITORY']}/{os.environ.get('GITHUB_REF_NAME', 'main')}/{dest}"
    for _ in range(24):
        try:
            if requests.head(url, timeout=15).status_code == 200:
                break
        except Exception:
            pass
        time.sleep(5)
    return url, dest


def check(r):
    if not r.ok:
        raise RuntimeError(f"{r.status_code} {r.text}")
    return r.json()


def ig_publish(url, caption):
    data = {"caption": caption, "access_token": TOKEN}
    if KIND == "reel":
        data.update(media_type="REELS", video_url=url, share_to_feed="true")
    else:
        data["image_url"] = url
    cid = check(requests.post(f"{GRAPH}/{IG}/media", data=data, timeout=60))["id"]
    for _ in range(40):
        s = check(requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code", "access_token": TOKEN}, timeout=30))
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram processing failed: {s}")
        time.sleep(15)
    return check(requests.post(f"{GRAPH}/{IG}/media_publish", data={"creation_id": cid, "access_token": TOKEN}, timeout=60))


def fb_publish(url, message):
    if KIND == "reel":
        r = requests.post(f"{GRAPH}/{PAGE}/videos", data={"file_url": url, "description": message, "access_token": TOKEN}, timeout=300)
    else:
        r = requests.post(f"{GRAPH}/{PAGE}/photos", data={"url": url, "message": message, "access_token": TOKEN}, timeout=120)
    return check(r)


def main():
    products = load_products()
    fallback = default_link()
    cands = [x for x in products if not x.get(f"posted_{KIND}") and (x.get("benable_link") or fallback)]
    cands.sort(key=lambda x: 0 if x.get("benable_link") else 1)  # jin ka apna link hai wo pehle
    if not cands:
        os.makedirs("out", exist_ok=True)
        with open("out/NO_PRODUCT.txt", "w", encoding="utf-8") as f:
            f.write(f"No eligible product found for {KIND}. Research workflow must add products first.\\n")
        print(f"No eligible product found for {KIND}; diagnostic saved in out/NO_PRODUCT.txt")
        return
    p = cands[0]
    link = p.get("benable_link") or fallback
    c = make_copy(p)
    ig_cap, fb_cap = captions(p, c, link)
    path = build_media(p, c)
    print("PRODUCT:", p["title"], "\n--- IG caption ---\n", ig_cap, "\n--- FB caption ---\n", fb_cap)
    if DRY:
        with open(f"out/{KIND}-preview.txt", "w", encoding="utf-8") as f:
            f.write(f"Product: {p['title']}\\nCategory: {p.get('category','')}\\nBenable profile: {link}\\n\\nInstagram caption:\\n{ig_cap}\\n\\nFacebook caption:\\n{fb_cap}\\n\\nMedia file: {path}\\n\\nPREVIEW ONLY — nothing was published.\\n")
        print("DRY RUN: media saved at", path)
        return
    url, dest = host(path)
    try:
        print("Instagram:", ig_publish(url, ig_cap))
        p[f"posted_{KIND}"] = True
        save_products(products)
        try:
            print("Facebook:", fb_publish(url, fb_cap))
        except Exception as e:
            print("Facebook failed (Instagram was posted):", e)
    finally:
        git("rm", "-f", dest)
        git("add", "products.json")
        git("commit", "-m", f"posted {KIND}: {p['title']}")
        git("pull", "--rebase")
        git("push")


if __name__ == "__main__":
    main()
