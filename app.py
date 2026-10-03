from flask import Flask, request, Response, send_from_directory
import urllib.request
import urllib.error
import os

# Папка, откуда отдаются index.html, servers.txt и прочая статика
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__, static_folder=None)

API_TARGETS = {
    "/api/shock":   "https://shockproject.pro/api/servers",
    "/api/myrust":  "https://myrust.ru/api/servers",
    "/api/bummer":  "https://bummerrust.com/api/v1/servers",
    "/api/yrs":     "https://yrsproject.gamestores.app/api/v1/widgets.monitoring",
    "/api/hirust":  "https://www.hirust.online/api/status",
    "/api/company": "https://companyrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/magix":   "https://magixrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/spectra": "https://spectraoffwipe.gamestores.app/api/v1/widgets.monitoring",
    "/api/sabr":    "https://sabrrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/dream":   "https://dreamrusttop.gamestores.app/api/v1/widgets.monitoring",
    "/api/sunfire": "https://sunfirenew.gamestores.app/api/v1/widgets.monitoring",
    "/api/wooh":    "https://woohrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/veil":    "https://veilrust.gamestores.app/api/v1/widgets.monitoring",
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


# Отдаём любые статические файлы (картинки, css, js) из корня проекта
@app.route("/<path:filename>")
def static_files(filename):
    # Не отдаём через этот маршрут API — они обрабатываются ниже
    if filename.startswith("api/"):
        return {"error": "Unknown endpoint"}, 404
    full = os.path.join(BASE_DIR, filename)
    if os.path.isfile(full):
        return send_from_directory(BASE_DIR, filename)
    return {"error": "Not found"}, 404


# ===================== API ПРОКСИ =====================

@app.route("/api/<name>")
def proxy(name):
    path = "/api/" + name
    if path not in API_TARGETS:
        return {"error": "Unknown endpoint"}, 404

    target = API_TARGETS[path]

    # Прокидываем query-параметры (например, ?name=MAGIX)
    if request.query_string:
        target += "?" + request.query_string.decode()

    try:
        req = urllib.request.Request(target, headers={
            "User-Agent": UA,
            "Accept": "application/json, text/plain, */*",
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
            ctype = r.headers.get("Content-Type", "application/json")

        resp = Response(body, content_type=ctype)
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "no-store"
        return resp

    except urllib.error.HTTPError as e:
        return {"error": "HTTP " + str(e.code)}, e.code
    except Exception as e:
        return {"error": str(e)}, 502


# ===================== ЗАПУСК =====================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
