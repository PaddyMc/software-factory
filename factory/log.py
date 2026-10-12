"""Live run log: every stage change, agent message, and tool call, written to
$FACTORY_HOME/logs/<task>.log and echoed to the terminal running `factory run`.
Follow from anywhere with `factory logs <task> -f`."""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path


def log_path(home: Path, task_id: str) -> Path:
    return home / "logs" / f"{task_id}.log"


def clip(text: str, n: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


class RunLog:
    def __init__(self, path: Path, echo: bool = True):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.echo = echo
        self._f = path.open("a", buffering=1)

    def __call__(self, tag: str, message: str) -> None:
        line = f"{dt.datetime.now():%H:%M:%S} [{tag}] {message}"
        self._f.write(line + "\n")
        if self.echo:
            print(line, file=sys.stdout, flush=True)

    def close(self) -> None:
        self._f.close()


class NullLog:
    def __call__(self, tag: str, message: str) -> None:
        pass

    def close(self) -> None:
        pass
