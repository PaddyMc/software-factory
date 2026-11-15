"""The loopback-only HTTP server and its socket-independent request application."""

from __future__ import annotations

import importlib.resources
import re
import secrets
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .. import config, observe
from ..db import ACTIVE, open_db, pid_alive
from ..scheduler import plan_pid_file
from . import jobs, views

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
QUICK_WAIT = 15.0
ACTIONS = {"sync", "status", "abandon", "requeue", "clean", "stop"}


class App:
    def __init__(self, home: Path, root: Path, launch=None):
        self.home = home
        self.root = root
        self.project = config.load(root).name
        self.port: int | None = None
        self.token = secrets.token_urlsafe(32)
        self.launch = launch or jobs.default_launch
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

    def _redirect(self, location: str):
        body = f'<p>See <a href="{views.esc(location)}">the next page</a>.</p>'.encode()
        return self._response(303, "text/html; charset=utf-8", body, [("Location", location)])

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

    @staticmethod
    def _query(path: str) -> dict[str, list[str]]:
        return parse_qs(path.split("?", 1)[1] if "?" in path else "", keep_blank_values=True)

    @staticmethod
    def _field(form: dict[str, list[str]], name: str, default: str = "") -> str:
        values = form.get(name)
        return values[0] if values else default

    def _notice_job(self, path: str):
        return jobs.get(self.home, self._field(self._query(path), "job"))

    def _origin_allowed(self, headers: dict[str, str]) -> bool:
        origin = headers.get("origin")
        if origin is None:
            return True
        port = self.port
        if port is None:
            host = headers.get("host", "")
            if ":" not in host:
                return False
            port_text = host.rsplit(":", 1)[1]
            if not port_text.isdigit():
                return False
            port = int(port_text)
        return origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    @staticmethod
    def _task_back(target: str):
        return f"Back to {target}", f"/tasks/{quote(target, safe='')}"

    def _validate(self, db, action: str, target: str):
        """Return (applies, reason, back link) without changing the board."""
        if action in ("sync", "status"):
            return True, "", ("Back to the board", "/")
        row = db.task(target)
        if action in ("abandon", "requeue", "clean") and row is None:
            return False, f"{target} isn't on this board", ("Back to the board", "/")
        if action == "abandon":
            if row["status"] not in ("queued", "failed"):
                return False, f"{target} is {row['status']}; only a queued or failed task can be put on hold", self._task_back(target)
            return True, "", self._task_back(target)
        if action == "requeue":
            if row["status"] != "abandoned":
                return False, f"{target} is {row['status']}; only a task on hold can be taken off hold", self._task_back(target)
            return True, "", self._task_back(target)
        if action == "clean":
            if row["status"] in ACTIVE and pid_alive(row["pid"]):
                return False, f"{target} is running; stop it first", self._task_back(target)
            if not (self.home / "worktrees" / target).exists():
                return False, f"{target} has no worktree to remove", self._task_back(target)
            return True, "", self._task_back(target)
        if action != "stop":
            return False, "That action isn't served by factory web.", ("Back to the board", "/")
        if row is not None:
            if row["status"] not in ACTIVE or not pid_alive(row["pid"]):
                return False, f"{target} is {row['status']}; nothing to stop", self._task_back(target)
            return True, "", self._task_back(target)

        rows = db.tasks()
        plan_rows = [item for item in rows
                     if target in (item["plan"], observe.plan_name(item["plan"]))]
        if not plan_rows:
            return False, f"{target} is neither a task on the board nor a plan", ("Back to the board", "/")
        name = observe.plan_name(plan_rows[0]["plan"])
        back = (f"Back to {name}", f"/#plan-{quote(name, safe='')}")
        if any(item["status"] in ACTIVE and pid_alive(item["pid"]) for item in plan_rows):
            return True, "", back
        try:
            plan_pid = int(plan_pid_file(self.home, name).read_text().strip())
            if plan_pid <= 0:
                raise ValueError("not a process id")
        except (FileNotFoundError, OSError, ValueError):
            plan_pid = None
        if pid_alive(plan_pid):
            return True, "", back
        return False, f"nothing to stop: {name} has no running plan run or task", back

    @staticmethod
    def _command(action: str, target: str):
        if action == "sync":
            return ["sync"], "factory sync", "quick", ""
        if action == "status":
            return ["status", "--refresh"], "factory status --refresh", "quick", ""
        if action == "abandon":
            note = "put on hold from factory web"
            return (["abandon", target, "--note", note],
                    f'factory abandon {target} --note "{note}"', "quick", target)
        if action == "requeue":
            return ["requeue", target], f"factory requeue {target}", "quick", target
        if action == "clean":
            return ["clean", target], f"factory clean {target}", "quick", target
        if action == "stop":
            return ["stop", target], f"factory stop {target}", "stop", target
        raise ValueError(action)

    def _post(self, action: str, headers: dict[str, str], body: bytes):
        if not self._origin_allowed(headers):
            return self._error(403, "Forbidden.", "This form came from another origin.")
        if "sec-fetch-site" in headers and headers["sec-fetch-site"] != "same-origin":
            return self._error(403, "Forbidden.", "Cross-site forms are not accepted.")
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/x-www-form-urlencoded":
            return self._error(415, "Unsupported media type.", "POST a URL-encoded factory form.")
        if len(body) > 16 * 1024:
            return self._error(413, "Content too large.", "A factory form is at most 16 KB.")
        form = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
        token = self._field(form, "token")
        if not token or not secrets.compare_digest(token, self.token):
            return self._error(403, "Forbidden.", "This form was not served by this factory web server.")
        if action not in ACTIONS:
            return self._error(404, "Page not found.", "That action isn't served by factory web.")

        target = self._field(form, "target")
        db = open_db(self.home, readonly=True)
        try:
            applies, why, back = self._validate(db, action, target)
        finally:
            db.close()
        if not applies:
            return self._error(409, "Action doesn't apply.", why, back=back)

        args, command, kind, job_target = self._command(action, target)
        argv = [sys.executable, "-m", "factory.cli", *args]
        job_id = jobs.start(self.home, self.root, argv, command, kind, job_target, self.launch)
        if kind == "stop":
            return self._redirect(f"/activity?job={job_id}")

        deadline = time.monotonic() + QUICK_WAIT
        while True:
            job = jobs.get(self.home, job_id)
            if job is None or job.result is not None or job.outcome == "lost":
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
        next_ = self._field(form, "next", "/")
        try:
            destination = urlsplit(next_)
        except ValueError:
            destination = None
        if (destination is None or destination.scheme or destination.netloc or destination.fragment
                or not destination.path.startswith("/") or next_.startswith("//") or "\\" in next_
                or "#" in next_ or any(ord(character) < 32 for character in next_)):
            next_ = "/"
        separator = "&" if "?" in next_ else "?"
        return self._redirect(f"{next_}{separator}job={job_id}")

    def handle(self, method: str, path: str, headers, body: bytes):
        """Answer one request without creating or accepting a socket."""
        normalized = {str(key).lower(): str(value) for key, value in headers.items()}
        request_path = path
        route = unquote(request_path.split("?", 1)[0])
        action_request = route.startswith("/actions/")
        if method == "POST" and action_request:
            if not self._local_host(normalized.get("host", "")):
                return self._error(403, "Forbidden.", "This server answers only requests for localhost.")
            return self._post(route[len("/actions/"):], normalized, body)
        if method not in ("GET", "HEAD"):
            allow = "GET, HEAD, POST" if action_request else "GET, HEAD"
            message = ("Only GET, HEAD and POST actions are answered." if action_request
                       else "Only GET and HEAD are answered.")
            return self._error(405, "Method not allowed.", message, [("Allow", allow)])
        if not self._local_host(normalized.get("host", "")):
            return self._error(403, "Forbidden.", "This server answers only requests for localhost.")

        path = route
        if path == "/":
            db = open_db(self.home, readonly=True)
            try:
                page = views.board(db, self.home, self.project, self.port, self.token,
                                   self._notice_job(request_path)).encode()
            finally:
                db.close()
            return self._response(200, "text/html; charset=utf-8", page)
        if path == "/activity":
            page = views.activity(self.home, self.project, self.port,
                                  self._notice_job(request_path)).encode()
            return self._response(200, "text/html; charset=utf-8", page)
        if path == "/confirm":
            query = self._query(request_path)
            action = self._field(query, "action")
            target = self._field(query, "target")
            if action not in ("stop", "clean") or not target:
                return self._error(404, "Page not found.", "That confirmation page isn't served by factory web.")
            db = open_db(self.home, readonly=True)
            try:
                applies, why, back = self._validate(db, action, target)
            finally:
                db.close()
            page = views.confirm(self.project, self.home, self.port, self.token,
                                 action, target, applies, why, back).encode()
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
                page = views.task(db, self.home, self.project, self.port, task_id, self.token,
                                  self._notice_job(request_path)).encode()
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
