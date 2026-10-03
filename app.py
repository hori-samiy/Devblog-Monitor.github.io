# app.py (переименуйте proxy.py или создайте новый)
from flask import Flask, request, Response
import urllib.request
import urllib.error

app = Flask(__name__)

API_TARGETS = {
    "/api/shock": "https://shockproject.pro/api/servers",
    # ... остальные URL
}

@app.route('/<path:path>')
def proxy(path):
    full_path = '/' + path
    if full_path in API_TARGETS:
        target = API_TARGETS[full_path]
        # обработка параметров name=...
        try:
            req = urllib.request.Request(target, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
            })
            with urllib.request.urlopen(req, timeout=15) as r:
                return Response(r.read(), content_type=r.headers.get("Content-Type", "application/json"))
        except Exception as e:
            return {"error": str(e)}, 502
    
    # Отдаём index.html для корня
    if full_path == '/':
        return app.send_static_file('index.html')
    return {"error": "Not found"}, 404