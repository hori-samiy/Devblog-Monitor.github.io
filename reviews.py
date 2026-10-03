"""Отзывы игроков: SQLite, один отзыв с одного IP на проект."""
import hashlib, os, re, sqlite3, time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
DB = os.path.join(DATA_DIR, "reviews.db")
# Соль для хеша IP (сами IP не хранятся). Задайте REVIEW_SALT в окружении.
SALT = os.environ.get("REVIEW_SALT", "change-me")
KEY_RE = re.compile(r"^[\w\-.%]{1,60}$", re.U)
MAX_PER_HOUR = 10


def _db():
    os.makedirs(DATA_DIR, exist_ok=True)
    c = sqlite3.connect(DB, timeout=10)
    c.execute("""CREATE TABLE IF NOT EXISTS reviews(
        project TEXT NOT NULL, iph TEXT NOT NULL, name TEXT NOT NULL,
        comment TEXT NOT NULL, vote TEXT NOT NULL, ts INTEGER NOT NULL,
        PRIMARY KEY(project, iph))""")
    return c


def _hash(ip):
    return hashlib.sha256((SALT + "|" + ip).encode()).hexdigest()


def get(project):
    with _db() as c:
        rows = c.execute("SELECT name,comment,vote,ts FROM reviews WHERE project=? ORDER BY ts DESC LIMIT 100", (project,)).fetchall()
        likes, dislikes = c.execute(
            "SELECT COALESCE(SUM(vote='like'),0), COALESCE(SUM(vote='dislike'),0) FROM reviews WHERE project=?", (project,)).fetchone()
    return {"likes": likes, "dislikes": dislikes,
            "reviews": [{"name": n, "comment": t, "vote": v, "ts": ts} for n, t, v, ts in rows]}


def summary():
    with _db() as c:
        rows = c.execute("SELECT project, SUM(vote='like'), SUM(vote='dislike') FROM reviews GROUP BY project").fetchall()
    return {p: {"likes": l, "dislikes": d} for p, l, d in rows}


def add(project, ip, name, comment, vote):
    """Возвращает (ответ, http-код)."""
    if not KEY_RE.match(project):
        return {"error": "Неизвестный проект"}, 404
    name = " ".join(str(name or "").split())[:30]
    comment = str(comment or "").strip()[:500]
    if vote not in ("like", "dislike"):
        return {"error": "Выберите лайк или дизлайк"}, 400
    if not name or not comment:
        return {"error": "Укажите имя и комментарий"}, 400
    iph, now = _hash(ip), int(time.time())
    with _db() as c:
        n = c.execute("SELECT COUNT(*) FROM reviews WHERE iph=? AND ts>?", (iph, now - 3600)).fetchone()[0]
        if n >= MAX_PER_HOUR:
            return {"error": "Слишком много отзывов, попробуйте позже"}, 429
        c.execute("INSERT OR REPLACE INTO reviews VALUES(?,?,?,?,?,?)", (project, iph, name, comment, vote, now))
    return get(project), 200
