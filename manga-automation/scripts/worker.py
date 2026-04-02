#!/usr/bin/env python3
"""
Python worker HTTP server.
n8n calls these endpoints instead of running docker exec.
Runs all Python scripts as in-process functions.

Endpoints:
    POST /fetch-trending        body: { limit: 20 }
    POST /fetch-chapter         body: { manga_id: 1 }
    POST /download-panels       body: { chapter_id: 1 }
    POST /check-duplicates      body: { chapter_id: 1 }
    POST /generate-video        body: { chapter_id: 1 }
    POST /upload-tiktok         body: { video_id: 1 }
    POST /detect-shadow-ban     body: {}
    GET  /health
"""
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from dotenv import load_dotenv

load_dotenv()

from scripts.utils.logger import setup_logger

logger = setup_logger("worker")

import scripts.fetch_trending_manga as fetch_trending
import scripts.fetch_chapter_images as fetch_chapter
import scripts.download_panels as download_panels
import scripts.check_duplicates as check_duplicates
import scripts.generate_video as generate_video
import scripts.upload_tiktok as upload_tiktok
import scripts.detect_shadow_ban as detect_shadow_ban
import scripts.upload_arbitrage as upload_arbitrage


ROUTES = {
    "/fetch-trending":    lambda body: fetch_trending.main(body.get("limit", 20)),
    "/fetch-chapter":     lambda body: fetch_chapter.main(body["manga_id"]),
    "/download-panels":   lambda body: download_panels.main(body["chapter_id"]),
    "/check-duplicates":  lambda body: check_duplicates.main(body["chapter_id"]),
    "/generate-video":    lambda body: generate_video.main(body["chapter_id"]),
    "/upload-tiktok":     lambda body: upload_tiktok.main(body["video_id"]),
    "/detect-shadow-ban": lambda body: detect_shadow_ban.main(
        body.get("min_posts", 5), body.get("threshold", 0.10)
    ),
    "/arbitrage/upload":  lambda body: upload_arbitrage.upload_arbitrage(body["asset_id"]),
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        logger.info(fmt % args)

    def send_json(self, code: int, data):
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "python-worker"})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            self.send_json(400, {"error": "invalid JSON body"})
            return

        handler = ROUTES.get(self.path)
        if not handler:
            self.send_json(404, {"error": f"unknown route {self.path}"})
            return

        try:
            result = handler(body)
            self.send_json(200, {"success": True, "result": result})
        except Exception as e:
            logger.error(f"Error in {self.path}: {e}\n{traceback.format_exc()}")
            self.send_json(500, {"success": False, "error": str(e)})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    server = HTTPServer(("0.0.0.0", port), Handler)
    logger.info(f"Python worker listening on port {port}")
    server.serve_forever()
