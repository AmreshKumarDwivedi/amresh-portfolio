"""
Amresh Portfolio — Flask backend
=================================
- Serves the portfolio (templates/index.html)
- POST /api/contact   -> saves contact form submissions to SQLite
- POST /api/track     -> records each page visit (with rate limiting)
- GET  /admin         -> Basic-Auth protected dashboard (visits + submissions)
- GET  /admin/api/data -> JSON data for the dashboard

Deps:  pip install -r requirements.txt
Run:   python app.py            (dev, port 5000)
Prod:  gunicorn app:app          (Render / any PaaS)

Env vars (set in Render dashboard or .env locally):
  ADMIN_USER         default 'admin'
  ADMIN_PASS         REQUIRED — set this to something strong
  SECRET_KEY         REQUIRED in prod — random string
  DATABASE_PATH      default './data.db'
"""
import os
import sqlite3
import hashlib
import re
import secrets
from datetime import datetime, date, timedelta
from functools import wraps
from flask import (
    Flask, request, jsonify, render_template,
    Response, g, abort
)

# ─── Config ──────────────────────────────────────────────────────────────
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(APP_DIR, "data.db"))

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "change-me-now")
SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(16))

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY


# ─── DB helpers ──────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables if they don't exist. Called once at startup."""
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS submissions (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at    TEXT NOT NULL,
        name          TEXT NOT NULL,
        email         TEXT NOT NULL,
        project_type  TEXT,
        budget        TEXT,
        message       TEXT NOT NULL,
        ip_hash       TEXT,
        user_agent    TEXT,
        is_read       INTEGER DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_sub_created ON submissions(created_at DESC);

    CREATE TABLE IF NOT EXISTS visits (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        visited_at  TEXT NOT NULL,
        date        TEXT NOT NULL,
        ip_hash     TEXT,
        path        TEXT,
        referrer    TEXT,
        user_agent  TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_visit_date ON visits(date);
    CREATE INDEX IF NOT EXISTS idx_visit_ip   ON visits(date, ip_hash);
    """)
    conn.commit()
    conn.close()


# ─── Utilities ───────────────────────────────────────────────────────────
def hash_ip(ip: str) -> str:
    """Privacy-friendly IP hashing (so we can detect uniques without storing raw IPs)."""
    salt = SECRET_KEY[:16]
    return hashlib.sha256((salt + (ip or "")).encode()).hexdigest()[:24]


def client_ip() -> str:
    # Render & most PaaS forward through X-Forwarded-For
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or ""


def require_basic_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth = request.authorization
        if (
            not auth
            or auth.username != ADMIN_USER
            or not secrets.compare_digest(auth.password or "", ADMIN_PASS)
        ):
            return Response(
                "Authentication required",
                401,
                {"WWW-Authenticate": 'Basic realm="Admin"'},
            )
        return f(*args, **kwargs)
    return wrapper


# ─── Routes: Public ──────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/api/contact", methods=["POST"])
def submit_contact():
    """Save a contact-form submission."""
    data = request.get_json(silent=True) or {}

    name = (data.get("name") or "").strip()[:80]
    email = (data.get("email") or "").strip().lower()[:120]
    project_type = (data.get("project_type") or "").strip()[:60]
    budget = (data.get("budget") or "").strip()[:30]
    message = (data.get("message") or "").strip()[:2000]

    # Validation
    if not name or len(name) < 2:
        return jsonify(ok=False, error="Please provide your name."), 400
    if not EMAIL_RE.match(email):
        return jsonify(ok=False, error="Please provide a valid email."), 400
    if not message or len(message) < 10:
        return jsonify(ok=False, error="Please tell me a bit more about your project."), 400

    # Lightweight rate limit: 1 submission per IP per 60 sec
    ip = client_ip()
    iph = hash_ip(ip)
    db = get_db()
    cutoff = (datetime.utcnow() - timedelta(seconds=60)).isoformat()
    recent = db.execute(
        "SELECT 1 FROM submissions WHERE ip_hash = ? AND created_at > ? LIMIT 1",
        (iph, cutoff),
    ).fetchone()
    if recent:
        return jsonify(ok=False, error="Please wait a moment before submitting again."), 429

    db.execute(
        """INSERT INTO submissions
           (created_at, name, email, project_type, budget, message, ip_hash, user_agent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.utcnow().isoformat(),
            name, email, project_type, budget, message,
            iph,
            (request.headers.get("User-Agent") or "")[:300],
        ),
    )
    db.commit()
    return jsonify(ok=True, message="Thanks! I'll reply within 24 hours.")


@app.route("/api/track", methods=["POST"])
def track_visit():
    """Record a single page visit. Idempotent-ish: ignored if same IP visited same path within 30 sec."""
    data = request.get_json(silent=True) or {}
    path = (data.get("path") or "/")[:200]
    ref = (data.get("ref") or "")[:300]

    ip = client_ip()
    iph = hash_ip(ip)
    today = date.today().isoformat()
    now = datetime.utcnow().isoformat()

    db = get_db()
    # De-dupe rapid repeats from same IP+path within 30 seconds
    cutoff = (datetime.utcnow() - timedelta(seconds=30)).isoformat()
    recent = db.execute(
        "SELECT 1 FROM visits WHERE ip_hash = ? AND path = ? AND visited_at > ? LIMIT 1",
        (iph, path, cutoff),
    ).fetchone()
    if recent:
        return jsonify(ok=True, deduped=True)

    db.execute(
        """INSERT INTO visits (visited_at, date, ip_hash, path, referrer, user_agent)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            now, today, iph, path, ref,
            (request.headers.get("User-Agent") or "")[:300],
        ),
    )
    db.commit()
    return jsonify(ok=True)


# ─── Routes: Admin ───────────────────────────────────────────────────────
@app.route("/admin")
@require_basic_auth
def admin_dashboard():
    return render_template("admin.html")


@app.route("/admin/api/data")
@require_basic_auth
def admin_data():
    """JSON payload for the admin dashboard."""
    db = get_db()

    # Overall counts
    total_visits = db.execute("SELECT COUNT(*) AS c FROM visits").fetchone()["c"]
    unique_visitors = db.execute(
        "SELECT COUNT(DISTINCT ip_hash) AS c FROM visits"
    ).fetchone()["c"]
    total_submissions = db.execute(
        "SELECT COUNT(*) AS c FROM submissions"
    ).fetchone()["c"]
    unread_submissions = db.execute(
        "SELECT COUNT(*) AS c FROM submissions WHERE is_read = 0"
    ).fetchone()["c"]

    today = date.today().isoformat()
    today_visits = db.execute(
        "SELECT COUNT(*) AS c FROM visits WHERE date = ?", (today,)
    ).fetchone()["c"]
    today_unique = db.execute(
        "SELECT COUNT(DISTINCT ip_hash) AS c FROM visits WHERE date = ?", (today,)
    ).fetchone()["c"]

    # Last 30 days
    thirty_days_ago = (date.today() - timedelta(days=29)).isoformat()
    daily_rows = db.execute(
        """SELECT date,
                  COUNT(*)                AS visits,
                  COUNT(DISTINCT ip_hash) AS uniques
           FROM visits
           WHERE date >= ?
           GROUP BY date
           ORDER BY date ASC""",
        (thirty_days_ago,),
    ).fetchall()
    by_date = {r["date"]: dict(r) for r in daily_rows}
    daily = []
    for i in range(30):
        d = (date.today() - timedelta(days=29 - i)).isoformat()
        row = by_date.get(d)
        daily.append({
            "date": d,
            "visits": row["visits"] if row else 0,
            "uniques": row["uniques"] if row else 0,
        })

    # Top referrers (last 30 days)
    refs = db.execute(
        """SELECT COALESCE(NULLIF(referrer,''), '(direct)') AS source, COUNT(*) AS c
           FROM visits
           WHERE date >= ?
           GROUP BY source
           ORDER BY c DESC
           LIMIT 8""",
        (thirty_days_ago,),
    ).fetchall()

    # Recent submissions
    subs = db.execute(
        """SELECT id, created_at, name, email, project_type, budget, message, is_read
           FROM submissions
           ORDER BY created_at DESC
           LIMIT 100"""
    ).fetchall()

    return jsonify(
        stats={
            "total_visits": total_visits,
            "unique_visitors": unique_visitors,
            "today_visits": today_visits,
            "today_unique": today_unique,
            "total_submissions": total_submissions,
            "unread_submissions": unread_submissions,
        },
        daily=daily,
        referrers=[dict(r) for r in refs],
        submissions=[dict(s) for s in subs],
    )


@app.route("/admin/api/submission/<int:sub_id>/read", methods=["POST"])
@require_basic_auth
def mark_read(sub_id):
    db = get_db()
    db.execute("UPDATE submissions SET is_read = 1 WHERE id = ?", (sub_id,))
    db.commit()
    return jsonify(ok=True)


@app.route("/admin/api/submission/<int:sub_id>", methods=["DELETE"])
@require_basic_auth
def delete_submission(sub_id):
    db = get_db()
    db.execute("DELETE FROM submissions WHERE id = ?", (sub_id,))
    db.commit()
    return jsonify(ok=True)


# ─── Health check (Render likes this) ────────────────────────────────────
@app.route("/healthz")
def health():
    return jsonify(ok=True, time=datetime.utcnow().isoformat())


# ─── Bootstrap ───────────────────────────────────────────────────────────
init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
