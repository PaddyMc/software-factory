"""The loopback-only HTTP server and its socket-independent request application."""

from __future__ import annotations

import importlib.resources
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote

from .. import config
from ..db import open_db
from . import views

CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
STATIC_TYPES = {
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
    "favicon.svg": "image/svg+xml",
    "fonts/dm-mono-400.woff2": "font/woff2",
    "fonts/dm-mono-500.woff2": "font/woff2",
    "fonts/hanken-grotesk-variable.woff2": "font/woff2",
    "fonts/instrument-serif-400.woff2": "font/woff2",
    "fonts/instrument-serif-400-italic.woff2": "font/woff2",
}


class App:
    def __init__(self, home: Path, root: Path):
        self.home = home
        self.root = root
        self.project = config.load(root).name
        self.port: int | None = None
        static = importlib.resources.files("factory.web") / "static"
        self.static = {name: (static / name).read_bytes() for name in STATIC_TYPES}

    def _response(self, status: int, content_type: str, body: bytes,
                  extra: list[tuple[str, str]] | None = None):
        headers = [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Content-Security-Policy", CSP),
            ("X-Content-Type-Options", "nosniff"),
            ("Referrer-Policy", "no-referrer"),
            ("Cache-Control", "no-store"),
        ]
        return status, headers + (extra or []), body

    def _error(self, status: int, title: str, message: str,
               extra: list[tuple[str, str]] | None = None, back=("Back to the board", "/")):
        page = views.error_page(self.project, self.home, self.port, title, message, back).encode()
        return self._response(status, "text/html; charset=utf-8", page, extra)

    @staticmethod
    def _local_host(value: str) -> bool:
        value = value.strip().lower()
        if not value or any(c.isspace() for c in value):
            return False
        if ":" in value:
            name, port = value.rsplit(":", 1)
            if not name or not port.isdigit():
                return False
        else:
            name = value
        return name in ("127.0.0.1", "localhost")

    def handle(self, method: str, path: str, headers, body: bytes):
        """Answer one request without creating or accepting a socket."""
        if method not in ("GET", "HEAD"):
            return self._error(405, "Method not allowed.", "Only GET and HEAD are answered.",
                               [("Allow", "GET, HEAD")])
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        if not self._local_host(normalized.get("host", "")):
            return self._error(403, "Forbidden.", "This server answers only requests for localhost.")

        path = unquote(path.split("?", 1)[0])
        if path == "/":
            db = open_db(self.home, readonly=True)
            try:
                page = views.board(db, self.home, self.project, self.port).encode()
            finally:
                db.close()
            return self._response(200, "text/html; charset=utf-8", page)
        run_match = re.fullmatch(r"/tasks/([^/]+)/runs/([^/]+)", path)
        if run_match:
            task_id, run_id = run_match.groups()
            db = open_db(self.home, readonly=True)
            try:
                if db.task(task_id) is None:
                    return self._error(404, "Page not found.", f"{task_id} isn't on this board")
                run = views.run_of(db, task_id, run_id)
                if run is None:
                    back = (f"Back to {task_id}", f"/tasks/{quote(task_id, safe='')}")
                    return self._error(404, "Page not found.",
                                       f"Run {run_id} isn't one of {task_id}'s runs", back=back)
                page = views.transcript(db, self.home, self.project, self.port, task_id, run).encode()
            finally:
                db.close()
            return self._response(200, "text/html; charset=utf-8", page)
        task_match = re.fullmatch(r"/tasks/([^/]+)", path)
        if task_match:
            task_id = task_match.group(1)
            db = open_db(self.home, readonly=True)
            try:
                if db.task(task_id) is None:
                    return self._error(404, "Page not found.", f"{task_id} isn't on this board")
                page = views.task(db, self.home, self.project, self.port, task_id).encode()
            finally:
                db.close()
            return self._response(200, "text/html; charset=utf-8", page)
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            if name in self.static:
                return self._response(200, STATIC_TYPES[name], self.static[name])
        return self._error(404, "Page not found.", "That page isn't served by factory web.")


def make_server(app: App, port: int) -> ThreadingHTTPServer:
    """Serve an App on loopback; port 0 asks the OS for a free port."""
    class Handler(BaseHTTPRequestHandler):
        def _respond(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            request_body = self.rfile.read(max(0, length)) if length else b""
            status, headers, response_body = app.handle(self.command, self.path, self.headers, request_body)
            self.send_response(status)
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD" and response_body:
                self.wfile.write(response_body)

        do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _respond
        do_CONNECT = do_TRACE = _respond

        def __getattr__(self, name):
            if name.startswith("do_"):
                return self._respond
            raise AttributeError(name)

        def log_message(self, format, *args):
            pass

        def log_error(self, format, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    app.port = server.server_address[1]
    return server
