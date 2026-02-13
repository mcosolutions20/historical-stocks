# backend/app/cache.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import RLock
from typing import Any, Dict, Optional, Tuple


# TTL for heavy portfolio computations
PERF_CACHE_TTL_SECONDS = int(os.getenv("PERF_CACHE_TTL_SECONDS", "60"))


@dataclass
class _CacheItem:
    value: Any
    expires_at: float


_lock = RLock()
_cache: Dict[str, _CacheItem] = {}

# Version tokens to invalidate per-portfolio cached computations
_portfolio_versions: Dict[int, int] = {}


def get_portfolio_version(portfolio_id: int) -> int:
    with _lock:
        return int(_portfolio_versions.get(int(portfolio_id), 0))


def bump_portfolio_version(portfolio_id: int) -> int:
    """Call this after any write that changes portfolio performance results."""
    pid = int(portfolio_id)
    with _lock:
        _portfolio_versions[pid] = int(_portfolio_versions.get(pid, 0)) + 1
        return _portfolio_versions[pid]


def _now() -> float:
    return time.time()


def cache_get(key: str) -> Optional[Any]:
    with _lock:
        item = _cache.get(key)
        if not item:
            return None
        if item.expires_at <= _now():
            _cache.pop(key, None)
            return None
        return item.value


def cache_set(key: str, value: Any, ttl_seconds: int) -> None:
    with _lock:
        _cache[key] = _CacheItem(value=value, expires_at=_now() + float(ttl_seconds))


def cache_clear_prefix(prefix: str) -> None:
    """Optional helper (not required)."""
    with _lock:
        keys = [k for k in _cache.keys() if k.startswith(prefix)]
        for k in keys:
            _cache.pop(k, None)

def get_portfolio_version(portfolio_id: int) -> int:
    with _lock:
        # start at 1 instead of 0 so “ver=0” never appears
        return int(_portfolio_versions.get(int(portfolio_id), 1))