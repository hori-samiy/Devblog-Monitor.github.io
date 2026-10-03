import http.server
import socketserver
import urllib.request
import urllib.parse
import urllib.error
import json
import reviews

API_TARGETS = {
    "/api/shock":     "https://shockproject.pro/api/servers",
    "/api/myrust":    "https://myrust.ru/api/servers",
    "/api/bummer":    "https://bummerrust.com/api/v1/servers",
    "/api/yrs":       "https://yrsproject.gamestores.app/api/v1/widgets.monitoring",
    "/api/hirust":    "https://www.hirust.online/api/status",
    "/api/company":   "https://companyrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/magix":     "https://magixrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/spectra":   "https://spectraoffwipe.gamestores.app/api/v1/widgets.monitoring",
    "/api/sabr":      "https://sabrrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/dream":     "https://dreamrusttop.gamestores.app/api/v1/widgets.monitoring",
    "/api/sunfire":   "https://sunfirenew.gamestores.app/api/v1/widgets.monitoring",
    "/api/wooh":      "https://woohrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/veil":      "https://veilrust.gamestores.app/api/v1/widgets.monitoring",
    "/api/old":       "https://oldrust.store/api/v1/widgets.monitoring",
}

PORT = 8000
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/reviews":
            self.reply(200, reviews.summary()); return
        if path.startswith("/api/reviews/"):
            self.reply(200, reviews.get(urllib.parse.unquote(path[len("/api/reviews/"):]))); return
        if path in API_TARGETS:
            self.proxy(API_TARGETS[path]); return
        low = path.lower()
        if low.startswith("/data/") or low.endswith((".py", ".db")):
            self.send_error(404); return
        super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if not path.startswith("/api/reviews/"):
            self.send_error(404); return
        try:
            n = min(int(self.headers.get("Content-Length", 0)), 4096)
            b = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            b = {}
        data, code = reviews.add(urllib.parse.unquote(path[len("/api/reviews/"):]), self.client_address[0],
                                 b.get("name"), b.get("comment"), b.get("vote"))
        self.reply(code, data)

    def reply(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode())

    def proxy(self, url):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                body = r.read()
                ctype = r.headers.get("Content-Type", "application/json")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "HTTP " + str(e.code)}).encode())
        except Exception as e:
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def log_message(self, fmt, *args):
        pass


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print("Сервер: http://localhost:%d" % PORT)
    print("Прокси API:", ", ".join(API_TARGETS.keys()))
    httpd.serve_forever()
