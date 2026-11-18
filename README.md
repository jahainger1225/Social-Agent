# Social Agent: setup guide

## 1. GitHub repository
1. github.com > New repository > naam `social-agent` > **Public** (zaroori: Instagram ko images ka public link chahiye. Aap ki keys Secrets mein rehti hain, wo public nahi hoti).
2. Is zip ko PC par extract karein. Repository mein **Add file > Upload files** par jayein aur extract kiya hua poora folder (`.github` folder samet) drag karke Commit karein.
   Agar `.github` folder upload na ho to Add file > Create new file mein naam `.github/workflows/post.yml` likh kar file ka text copy-paste karein (reel.yml aur research.yml ke liye bhi).

## 2. Secrets (Settings > Secrets and variables > Actions > New repository secret)
| Naam | Kya daalna hai |
|---|---|
| GEMINI_API_KEY | aistudio.google.com ki key |
| META_TOKEN | Long-lived Facebook Page access token |
| IG_USER_ID | Instagram Business Account ID |
| FB_PAGE_ID | Facebook Page ID |

Settings > Actions > General > Workflow permissions mein **Read and write permissions** select karein.

## 3. Test (pehle dry-run)
1. Actions tab > **research** > Run workflow. 1-2 minute baad repo mein `TODAY.md` aur `products.json` update hongi.
2. `products.json` mein kisi product ke `"benable_link"` mein apna Benable link paste karein (Edit icon > Commit).
3. Actions > **post** > Run workflow (dry_run tick rahne dein). Run khatam hone par neeche **preview** artifact download karke image dekh lein, aur log mein caption padh lein.
4. Sab theek ho to dry_run ka tick hata kar dobara chalayein. Ye asli post karega.
5. Reel ke liye **reel** workflow ke saath yehi karein.

## 4. Roz ka kaam (5 minute)
- Subah `TODAY.md` kholein, 3 products Benable mein add karein, aur links `products.json` mein paste karein.
- Posts roz khud nikalti hain: 3 posts (1 PM, 6 PM, 12 AM Pakistan time) aur 2 reels (6 PM, 6 AM).

## 5. Warm-up
Pehle hafte sirf 1 post + 1 reel rakhein: `post.yml` mein 2 cron lines aur `reel.yml` mein 1 cron line hata dein. Phir dheere dheere wapas lagayein.

## Dhyan rakhein
- Instagram bio mein apna Benable link lagayein.
- Instagram par post ke baad Pinterest mein pin khud banta hai (aap ne Pinterest se Instagram link kiya hua hai).
- Agar Gemini ka model purana ho jaye to repo mein variable `GEMINI_MODEL` set karein.
- Meta Graph API ka version `GRAPH_VERSION` se badal sakte hain (default v23.0).
