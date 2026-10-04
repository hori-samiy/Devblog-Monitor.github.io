"""Анкеты проектов: валидация, лимит 3 в сутки на IP, отправка в Discord через webhook."""
import hashlib, json, os, re, sqlite3, time, urllib.request, urllib.error, uuid

import reviews  # переиспользуем соль, папку данных и хеш IP

# Вставьте ссылку вебхука между кавычками ниже (или задайте переменную окружения DISCORD_WEBHOOK_URL).
# Имя "DISCORD_WEBHOOK_URL" не менять!
WEBHOOK_URL = "https://discord.com/api/webhooks/1555983529223921775/q4HWWjZqiEy9TK22gcnQ0gmG40tMaxbdIXkPpu0WA6uUhCh66L4svDMLo8iLhmQkG-_m"
WEBHOOK = (os.environ.get("DISCORD_WEBHOOK_URL") or WEBHOOK_URL).strip()
MAX_PER_DAY = 3
WINDOW = 24 * 3600
MAX_FILES = 10
MAX_FILE = 5 * 1024 * 1024      # 5 МБ на файл
MAX_TOTAL = 8 * 1024 * 1024     # лимит Discord на сообщение без буста — держим запас

LIMITS = {"name": 80, "site": 200, "tags": 200, "desc": 1000, "socials": 500, "icon": 300, "dev": 20}
URL_RE = re.compile(r"^https?://[^\s]+\.[^\s]+$", re.I)

UA = "Mozilla/5.0 (compatible; DevblogMonitor/1.0)"


def _db():
    c = reviews._db()
    c.execute("CREATE TABLE IF NOT EXISTS submissions(iph TEXT NOT NULL, ts INTEGER NOT NULL)")
    c.execute("CREATE INDEX IF NOT EXISTS sub_iph ON submissions(iph, ts)")
    return c


def _sniff(data):
    """Расширение по сигнатуре файла; None — если это не картинка."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _clean(v, key):
    return " ".join(str(v or "").split())[:LIMITS[key]]


def _multipart(payload, files):
    boundary = "----dm" + uuid.uuid4().hex
    out = []

    def part(headers, body):
        out.append(("--" + boundary + "\r\n" + headers + "\r\n\r\n").encode())
        out.append(body if isinstance(body, bytes) else body.encode())
        out.append(b"\r\n")

    part('Content-Disposition: form-data; name="payload_json"\r\nContent-Type: application/json',
         json.dumps(payload, ensure_ascii=False))
    for i, (fname, data) in enumerate(files):
        part('Content-Disposition: form-data; name="files[%d]"; filename="%s"\r\nContent-Type: application/octet-stream' % (i, fname), data)
    out.append(("--" + boundary + "--\r\n").encode())
    return b"".join(out), "multipart/form-data; boundary=" + boundary


def _send(f, files):
    fields = [
        ("Название", f["name"]), ("Сайт", f["site"]), ("Теги", f["tags"]),
        ("Описание", f["desc"]), ("Соцсети", f["socials"]), ("Иконка", f["icon"]),
        ("Devblog", f["dev"]),
        ("Скриншоты", "%d шт. (во вложениях)" % len(files) if files else "не приложены"),
    ]
    embed = {
        "title": "Новая анкета: " + f["name"],
        "color": 0x738DFF,
        "fields": [{"name": n, "value": (v or "—")[:1024], "inline": n in ("Devblog", "Скриншоты")} for n, v in fields],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    payload = {"embeds": [embed], "allowed_mentions": {"parse": []}}
    if files:
        payload["attachments"] = [{"id": i, "filename": n} for i, (n, _) in enumerate(files)]
    body, ctype = _multipart(payload, files)
    req = urllib.request.Request(WEBHOOK, data=body, method="POST",
                                 headers={"Content-Type": ctype, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return 200 <= r.status < 300


def submit(ip, form, uploads):
    """form — dict полей, uploads — список (filename, bytes). Возвращает (ответ, http-код)."""
    if not WEBHOOK:
        return {"error": "Приём анкет не настроен (нет DISCORD_WEBHOOK_URL)"}, 503

    # honeypot: боты заполняют скрытое поле — молча «принимаем»
    if str(form.get("website2") or "").strip():
        return {"ok": True}, 200

    f = {k: _clean(form.get(k), k) for k in LIMITS}
    # описание может быть многострочным — сохраняем переносы
    f["desc"] = "\n".join(" ".join(l.split()) for l in str(form.get("desc") or "").strip().splitlines() if l.strip())[:LIMITS["desc"]]

    labels = {"name": "Название", "site": "Сайт", "tags": "Теги", "desc": "Описание",
              "socials": "Соцсети", "icon": "Иконка", "dev": "Devblog"}
    for k, label in labels.items():
        if not f[k]:
            return {"error": "Заполните поле «%s»" % label}, 400
    if not URL_RE.match(f["site"]):
        return {"error": "Сайт должен быть ссылкой http(s)://…"}, 400
    if not URL_RE.match(f["icon"]):
        return {"error": "Иконка должна быть ссылкой http(s)://…"}, 400

    if len(uploads) > MAX_FILES:
        return {"error": "Не больше %d скриншотов" % MAX_FILES}, 400
    files, total = [], 0
    for n, (_, data) in enumerate(uploads, 1):
        if len(data) > MAX_FILE:
            return {"error": "Скриншот больше 5 МБ"}, 413
        ext = _sniff(data)
        if not ext:
            return {"error": "Скриншоты — только PNG, JPG, GIF или WEBP"}, 400
        total += len(data)
        files.append(("screenshot%d.%s" % (n, ext), data))
    if total > MAX_TOTAL:
        return {"error": "Скриншоты суммарно больше 8 МБ"}, 413

    iph, now = reviews._hash(ip), int(time.time())
    with _db() as c:
        c.execute("DELETE FROM submissions WHERE ts<?", (now - WINDOW,))
        n = c.execute("SELECT COUNT(*) FROM submissions WHERE iph=? AND ts>?", (iph, now - WINDOW)).fetchone()[0]
        if n >= MAX_PER_DAY:
            return {"error": "Лимит: не больше %d анкет в сутки с одного IP. Попробуйте завтра." % MAX_PER_DAY}, 429
        cur = c.execute("INSERT INTO submissions VALUES(?,?)", (iph, now))
        rid = cur.lastrowid

    try:
        _send(f, files)
    except Exception:
        # не удалось доставить — попытку не засчитываем
        with _db() as c:
            c.execute("DELETE FROM submissions WHERE rowid=?", (rid,))
        return {"error": "Не удалось отправить анкету, попробуйте позже"}, 502
    return {"ok": True, "left": MAX_PER_DAY - n - 1}, 200