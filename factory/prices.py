"""Per-token prices for cost tracking. OpenRouter publishes them at /api/v1/models
(no key needed); the table is cached under $FACTORY_HOME/cache for a day.
Unknown models or an unreachable price list yield no cost, never an error."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

from . import factory_home

OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
MAX_AGE = 24 * 3600
_memo: dict[str, dict] = {}


def cache_path() -> Path:
    return factory_home() / "cache" / "openrouter-prices-v2.json"


def _fetch() -> dict:
    with urllib.request.urlopen(OPENROUTER_MODELS, timeout=10) as r:
        data = json.load(r)["data"]
    table = {}
    for m in data:
        pr = m.get("pricing") or {}
        if "prompt" not in pr or "completion" not in pr:
            continue
        entry = {"prompt": float(pr["prompt"]), "completion": float(pr["completion"])}
        if pr.get("input_cache_read") not in (None, ""):
            entry["cache_read"] = float(pr["input_cache_read"])
        table[m["id"]] = entry
    return table


def openrouter_table() -> dict:
    path = cache_path()
    key = str(path)
    if key in _memo:
        return _memo[key]
    table: dict = {}
    if path.is_file() and time.time() - path.stat().st_mtime < MAX_AGE:
        table = json.loads(path.read_text())
    else:
        try:
            table = _fetch()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(table))
        except Exception:  # offline or API change: costs are simply unknown
            table = json.loads(path.read_text()) if path.is_file() else {}
    _memo[key] = table
    return table


def per_token(spec: str) -> dict | None:
    """{prompt, completion[, cache_read]} USD per token for a `provider:model` spec, if known."""
    provider, _, model = spec.partition(":")
    if provider != "openrouter":
        return None
    return openrouter_table().get(model)


def cost(spec: str, tokens_in: int, tokens_out: int, cache_read: int = 0) -> float | None:
    """USD for one model call; cached input tokens use the cache-read price when the model has one."""
    rate = per_token(spec)
    if rate is None:
        return None
    cached = min(cache_read, tokens_in) if "cache_read" in rate else 0
    return (tokens_in - cached) * rate["prompt"] + cached * rate.get("cache_read", 0) + tokens_out * rate["completion"]
