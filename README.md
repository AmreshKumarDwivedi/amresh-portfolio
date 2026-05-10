# Amresh Kumar Dwivedi — Portfolio + Backend

Full-stack portfolio site with contact form storage, visitor tracking, and a
password-protected admin dashboard. Built to run on the **cheapest possible
infrastructure**.

---

## What's inside

```
.
├── app.py                  # Flask backend (~250 lines)
├── requirements.txt        # Python deps (Flask + gunicorn — that's it)
├── Procfile                # Start command for any PaaS
├── render.yaml             # One-click deploy to Render
├── templates/
│   ├── index.html          # Portfolio (warm dark + cream sections)
│   └── admin.html          # Admin dashboard (stats, chart, submissions)
├── .env.example            # Sample env vars
└── .gitignore
```

**Tech stack:**
- **Language:** Python 3.11+ (Flask)
- **Database:** SQLite (single file, zero config, zero cost)
- **Server:** Gunicorn (production WSGI)

---

## Why Python + Flask + SQLite?

You asked for the cheapest stack to run. Here's why this combo wins:

| Concern        | Why this stack is cheap |
|----------------|--------------------------|
| **RAM**        | Flask + gunicorn idles at ~30–50 MB. Fits any free tier. |
| **CPU**        | Python is plenty fast for a portfolio (hundreds of requests/sec on a single core). |
| **Database**   | SQLite is just a file. **No separate database server**, no DB hosting bill. |
| **Deps**       | Only 2 packages. Build is fast → free build minutes go further. |
| **Hosting**    | Runs on every free tier: Render, PythonAnywhere, Fly.io, Railway, Oracle Cloud. |

> Cheaper alternatives considered: PHP shared hosting (~$1–3/mo at Hostinger/Namecheap)
> is technically cheaper to run, but lacks the modern dev workflow (no git deploy,
> no env vars in a UI). For a portfolio with a simple admin, Python on a free PaaS
> is the better trade-off.

---

## Cheapest server recommendations (ranked)

### 🥇 #1 — **Render Free Tier** ($0/month) — *recommended*
- **Cost:** Free, forever
- **Caveats:** Web service spins down after 15 min idle (~50 sec cold start on first visit), 750 free hours/month
- **Storage:** Free tier has ephemeral disk → SQLite **resets on redeploy**. Fine for the first months. Once you start getting real submissions, upgrade to Render's $7/month Starter plan + 1 GB persistent disk ($1/month) = **$8/mo total** with persistence.
- **Setup:** Push to GitHub → connect repo → done. `render.yaml` is included.

### 🥈 #2 — **Oracle Cloud "Always Free"** ($0/month forever, no cold starts)
- **Cost:** Free forever, 4 ARM CPUs + 24 GB RAM (genuinely insane free tier)
- **Caveats:** More setup — you SSH in, install Python, configure nginx + systemd yourself
- **Best if:** You want zero cold starts and can spend ~1 hour on initial setup
- **Persistence:** SQLite file lives on the VM disk = always persistent

### 🥉 #3 — **Fly.io Free Allowance** ($0–$2/month)
- 3 shared-cpu VMs free, persistent volume up to 3 GB free
- No cold starts
- Slightly more deploy complexity than Render

### #4 — **Cheapest paid VPS — Hetzner CX22** (€4.51 ≈ $5/month)
- 2 vCPU, 4 GB RAM, 40 GB SSD, 20 TB bandwidth in Europe
- Full control, never sleeps, runs anything
- Best $/performance in the industry as of 2026

### My pick for you
**Start on Render free tier today.** Once you start receiving regular leads
(the moment SQLite resetting on redeploy becomes painful), move to either:
- Render Starter + persistent disk ($8/mo) — easiest, or
- Oracle Cloud Always Free ($0) — most generous, more setup work.

---

## Local setup (5 minutes)

```bash
# 1. Install deps
python3 -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Set env vars
cp .env.example .env
# Edit .env — set ADMIN_PASS to something strong

# 3. Run
export ADMIN_PASS=$(grep ADMIN_PASS .env | cut -d= -f2)
export SECRET_KEY=$(grep SECRET_KEY .env | cut -d= -f2)
python app.py
# → http://localhost:5000
# → http://localhost:5000/admin   (login with admin / your password)
```

---

## Deploy to Render in 4 steps

1. **Push this folder to a GitHub repo.**

2. Go to [render.com](https://render.com) → **New +** → **Blueprint** → connect your repo.
   Render reads `render.yaml` and provisions everything automatically.

3. After the first deploy, open the service → **Environment** tab.
   You'll see `ADMIN_PASS` was auto-generated — **copy that password** (you'll need it for `/admin`).

4. Visit `https://your-service.onrender.com` → site is live.
   Visit `/admin` → use `admin` + the auto-generated password to log in.

> ⚠️ **About persistent disk:** the `disk:` block in `render.yaml` requires a paid plan ($7/mo).
> If you stay on free tier, **remove that disk block** — but know that your SQLite database
> will reset every time you redeploy. Use the free tier for testing, upgrade once it goes live.

---

## How it works

### Visitor tracking (`POST /api/track`)
The portfolio fires a single `fetch('/api/track')` on page load. The backend:
- Hashes the visitor's IP with a salted SHA-256 (privacy-friendly, no raw IP storage)
- De-dupes the same IP+path within 30 seconds (prevents inflation)
- Stores: timestamp, date, IP hash, path, referrer, user-agent

### Contact form (`POST /api/contact`)
- Validates name, email format, message (≥10 chars)
- Rate-limits: 1 submission per IP per 60 seconds
- Stores everything in `submissions` table

### Admin dashboard (`GET /admin`)
Protected by HTTP Basic Auth (browser pops a login dialog). Shows:
- 4 stat cards: total visits, unique visitors, today's visits, submission count
- 30-day visit chart (hover bars for daily breakdown)
- Top traffic sources (referrers)
- Full list of submissions with mark-as-read / delete / one-click reply

---

## API reference

| Method | Endpoint                            | Auth        | Purpose |
|--------|-------------------------------------|-------------|---------|
| GET    | `/`                                 | —           | Portfolio |
| POST   | `/api/track`                        | —           | Record visit |
| POST   | `/api/contact`                      | —           | Submit form |
| GET    | `/admin`                            | Basic Auth  | Dashboard UI |
| GET    | `/admin/api/data`                   | Basic Auth  | JSON for dashboard |
| POST   | `/admin/api/submission/<id>/read`   | Basic Auth  | Mark read |
| DELETE | `/admin/api/submission/<id>`        | Basic Auth  | Delete submission |
| GET    | `/healthz`                          | —           | Health check |

---

## Customization

- **Change colors:** edit the `:root { --bg: ... }` block in `templates/index.html`
- **Add fields to the form:** add an `<input>` in `index.html`, then add the column to the `submissions` table in `app.py` (`init_db()`) and to the INSERT in `submit_contact()`
- **Email yourself on new submissions:** add SMTP send in `submit_contact()` after the DB insert (use a free Brevo / Resend / Mailgun account)

---

## Cost summary

| Setup                                | Monthly cost |
|--------------------------------------|--------------|
| Render Free (with cold starts, no persistence) | **$0** |
| Render Starter + 1 GB disk           | $8 |
| Oracle Cloud Always Free             | **$0** (forever) |
| Hetzner CX22 VPS                     | ~$5 |
| Fly.io free allowance                | $0–2 |

For a portfolio site with low-to-moderate traffic, **the free tier of any of these
will handle hundreds of visitors per day comfortably.**

---

Built with Flask, SQLite, and a strong opinion that simple stacks beat complex ones.
