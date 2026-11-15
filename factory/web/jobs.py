"""Detached factory commands started by the web interface."""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

from ..db import pid_alive

JOB_NAME = re.compile(r"\d{6}")
_LOCK = threading.Lock()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text())
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _directory(home: Path, job_id: str) -> Path:
    return home / "web" / "jobs" / job_id


def default_launch(argv: list[str], cwd: Path):
    """Start the job runner in its own session, with no connection to the server's terminal."""
    return subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)


def prune(home: Path, keep: int = 200) -> None:
    """Keep only the newest numbered job directories."""
    root = home / "web" / "jobs"
    try:
        names = sorted((path for path in root.iterdir()
                        if path.is_dir() and JOB_NAME.fullmatch(path.name)),
                       key=lambda path: int(path.name), reverse=True)
    except FileNotFoundError:
        return
    for path in names[max(0, keep):]:
        shutil.rmtree(path, ignore_errors=True)


def start(home: Path, root: Path, argv: list[str], command: str, kind: str, target: str,
          launch=default_launch) -> str:
    """Record and detach one factory command, returning its six-digit job id."""
    with _LOCK:
        parent = home / "web" / "jobs"
        parent.mkdir(parents=True, exist_ok=True)
        existing = [int(path.name) for path in parent.iterdir()
                    if path.is_dir() and JOB_NAME.fullmatch(path.name)]
        job_id = f"{max(existing, default=0) + 1:06d}"
        directory = _directory(home, job_id)
        directory.mkdir()
        record = {
            "argv": list(argv),
            "command": command,
            "kind": kind,
            "target": target,
            "started_at": _now(),
            "pid": None,
            "root": str(root),
        }
        _write_json(directory / "job.json", record)
        (directory / "output.log").touch()
        prune(home)
        process = launch([sys.executable, "-m", "factory.web.jobs", str(directory)], cwd=root)
        record["pid"] = process.pid
        _write_json(directory / "job.json", record)
        return job_id


@dataclass
class Job:
    id: str
    command: str
    kind: str
    target: str
    started_at: str
    pid: int | None
    result: dict | None
    directory: Path

    @property
    def outcome(self) -> str:
        if self.result is None:
            return "running" if pid_alive(self.pid) else "lost"
        code = self.result.get("exit")
        return "done" if code == 0 else f"exit {code}"

    def output(self, limit: int = 200) -> list[str]:
        try:
            lines = (self.directory / "output.log").read_text(errors="replace").splitlines()
        except (FileNotFoundError, OSError):
            return []
        return lines[-limit:] if limit else []


def _job(home: Path, directory: Path) -> Job | None:
    record = _read_json(directory / "job.json")
    if record is None:
        return None
    try:
        return Job(
            id=directory.name,
            command=str(record["command"]),
            kind=str(record["kind"]),
            target=str(record["target"]),
            started_at=str(record["started_at"]),
            pid=record.get("pid"),
            result=_read_json(directory / "result.json"),
            directory=directory,
        )
    except (KeyError, TypeError, ValueError):
        return None


def get(home: Path, job_id: str | None) -> Job | None:
    if not job_id or not JOB_NAME.fullmatch(job_id):
        return None
    return _job(home, _directory(home, job_id))


def load(home: Path) -> list[Job]:
    """Read every intact job, newest first; a concurrent partial write is simply omitted."""
    root = home / "web" / "jobs"
    try:
        directories = sorted((path for path in root.iterdir()
                              if path.is_dir() and JOB_NAME.fullmatch(path.name)),
                             key=lambda path: int(path.name), reverse=True)
    except FileNotFoundError:
        return []
    return [job for directory in directories if (job := _job(home, directory)) is not None]


def main(argv: list[str]) -> int:
    """Run the command belonging to one job directory and record its outcome."""
    if len(argv) != 1:
        return 2
    directory = Path(argv[0])
    record = _read_json(directory / "job.json")
    if record is None:
        return 2
    code = 127
    try:
        with (directory / "output.log").open("a") as output:
            try:
                completed = subprocess.run(record["argv"], cwd=record["root"], stdin=subprocess.DEVNULL,
                                           stdout=output, stderr=subprocess.STDOUT)
                code = completed.returncode
            except OSError as error:
                output.write(f"{error}\n")
                output.flush()
    finally:
        _write_json(directory / "result.json", {"exit": code, "ended_at": _now()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
