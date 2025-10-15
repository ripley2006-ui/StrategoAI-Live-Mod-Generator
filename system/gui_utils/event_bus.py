"""Tiny in-process pub/sub for UI modules.

Usage:
- subscribe(event, callback): register a callable
- unsubscribe(event, callback): remove
- publish(event, *args, **kwargs): notify listeners (best-effort)

Thread-safety: minimal; uses a lock around the subscribers map. Callbacks are
invoked in the caller thread, so UI code should hop to the main loop if needed.
"""

from __future__ import annotations

from typing import Callable, Dict, List, DefaultDict
from collections import defaultdict
import threading

_subs: DefaultDict[str, List[Callable[..., None]]] = defaultdict(list)
_lock = threading.Lock()


def subscribe(event: str, callback: Callable[..., None]) -> None:
    with _lock:
        if callback not in _subs[event]:
            _subs[event].append(callback)


def unsubscribe(event: str, callback: Callable[..., None]) -> None:
    with _lock:
        if callback in _subs[event]:
            _subs[event].remove(callback)
        if not _subs[event]:
            _subs.pop(event, None)


def publish(event: str, *args, **kwargs) -> None:
    # Snapshot to minimize lock time
    with _lock:
        listeners = list(_subs.get(event, ()))
    for cb in listeners:
        try:
            cb(*args, **kwargs)
        except Exception:
            # best-effort bus; never crash caller
            pass

