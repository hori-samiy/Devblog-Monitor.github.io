from flask import Flask, request, Response, send_from_directory, jsonify
import reviews
import submissions
import urllib.request
import urllib.error
import json as _json
import os

# Папка, откуда отдаются index.html, servers.txt и прочая статика
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # анкета со скриншотами

# Значение — либо строка (один URL), либо список строк (несколько URL).
# Несколько URL опрашиваются параллельно, ответы склеиваются в JSON-массив.
API_TARGETS = {
    "/api/shock":   "https://shockproject.pro/api/servers",
    "/api/myrust":  "https://myrust.ru/api/servers",
    "/api/bummer":  "https://bummerrust.com/api/v1/servers",
    "/api/yrs":     [
        "https://api.yrsproject.ru/public/server/GetInfo/185.207.214.78/35000",
        "https://api.yrsproject.ru/public/server/GetInfo/185.207.214.78/35001",
    ],
    "/api/hirust":  "https://www.hirust.online/api/status",
    "/api/company": "https://companyrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/magix":   "https://magixrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/spectra": "https://spectraoffwipe.gamestores.app/api/v1/widgets.monitoring",
    "/api/sabr":    "https://sabrrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/dream":   "https://dreamrusttop.gamestores.app/api/v1/widgets.monitoring",
    "/api/sunfire": "https://sunfirenew.gamestores.app/api/v1/widgets.monitoring",
    "/api/wooh":    "https://woohrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/veil":    "https://veilrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/old":     "https://oldrust.store/api/v1/widgets.monitoring",
    "/api/snow":    "https://free-rust.pro/api/servers.json",
}

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


# ===================== СТАТИКА =====================

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.route("/servers.txt")
def servers_txt():
    return send_from_directory(BASE_DIR, "servers.txt")


@app.route("/serverwipe.txt")
def serverwipe_txt():
    return send_from_directory(BASE_DIR, "serverwipe.txt")


# Отдаём любые статические файлы (картинки, css, js) из корня проекта
@app.route("/<path:filename>")
def static_files(filename):
    # Не отдаём через этот маршрут API — они обрабатываются ниже
    if filename.startswith("api/"):
        return {"error": "Unknown endpoint"}, 404
    # Не отдаём исходники, базу отзывов и служебные файлы
    low = filename.lower()
    if low.startswith("data/") or low.endswith((".py", ".db", ".txt")) and low != "servers.txt" or low.startswith("."):
        return {"error": "Not found"}, 404
    full = os.path.join(BASE_DIR, filename)
    if os.path.isfile(full):
        return send_from_directory(BASE_DIR, filename)
    return {"error": "Not found"}, 404


# ===================== API ПРОКСИ =====================

def client_ip():
    # За прокси берём ПОСЛЕДНИЙ адрес из X-Forwarded-For (его дописал наш прокси, клиент подделать не может)
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[-1].strip()
    return request.remote_addr or "0.0.0.0"


@app.route("/api/reviews")
def reviews_summary():
    return jsonify(reviews.summary())


@app.route("/api/reviews/<project>", methods=["GET", "POST"])
def project_reviews(project):
    if request.method == "GET":
        return jsonify(reviews.get(project))
    body = request.get_json(silent=True) or {}
    data, code = reviews.add(project, client_ip(), body.get("name"), body.get("comment"), body.get("vote"))
    return jsonify(data), code


@app.route("/api/submit", methods=["POST"])
def submit_form():
    uploads = [(f.filename, f.read(submissions.MAX_FILE + 1)) for f in request.files.getlist("shots") if f and f.filename]
    data, code = submissions.submit(client_ip(), request.form, uploads)
    return jsonify(data), code


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "Файлы слишком большие (максимум 8 МБ суммарно)"}), 413


@app.route("/api/<name>")
def proxy(name):
    path = "/api/" + name
    if path not in API_TARGETS:
        return {"error": "Unknown endpoint"}, 404

    targets = API_TARGETS[path]
    if isinstance(targets, str):
        targets = [targets]

    # Прокидываем query-параметры (например, ?name=MAGIX) в каждый URL
    qs = ("?" + request.query_string.decode()) if request.query_string else ""

    responses = []  # список кортежей (body | None, ctype | error)
    for target in targets:
        url = target + qs
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "application/json")
            responses.append((body, ctype))
        except urllib.error.HTTPError as e:
            responses.append((None, "HTTP " + str(e.code)))
        except Exception as e:
            responses.append((None, str(e)))

    # Один URL — отдаём как раньше, без обёртки (фронт получит тот же формат, что и раньше)
    if len(responses) == 1:
        body, ctype = responses[0]
        if body is None:
            return {"error": ctype}, 502
        resp = Response(body, content_type=ctype)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    # Несколько URL — склеиваем JSON-ответы в массив.
    # Ошибки тоже попадают в массив как {"error": "..."},
    # чтобы фронт мог их проигнорировать и использовать успешные ответы.
    merged = []
    for body, ctype in responses:
        if body is None:
            merged.append({"error": ctype})
        else:
            try:
                merged.append(_json.loads(body.decode("utf-8", "replace")))
            except Exception:
                merged.append({"raw": body.decode("utf-8", "replace")})

    resp = Response(_json.dumps(merged, ensure_ascii=False), content_type="application/json")
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
