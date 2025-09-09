import random
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional

try:
    import redis
except Exception:  # pragma: no cover - optional in dev
    redis = None  # type: ignore


@dataclass
class RateWindow:
    key: str
    limit: int
    window_seconds: int


class RedisRateLimiter:
    def __init__(self, client: "redis.Redis"):
        self.client = client

    def allow(self, window: RateWindow) -> bool:
        now = int(time.time())
        bucket = now // window.window_seconds
        k = f"rl:{window.key}:{bucket}"
        with self.client.pipeline() as p:
            p.incr(k)
            p.expire(k, window.window_seconds * 2)
            cnt, _ = p.execute()
        return int(cnt) <= window.limit

    def wait(self, window: RateWindow, max_sleep: float = 5.0) -> None:
        # Busy-wait with jitter until allowed, but cap sleep per loop
        while not self.allow(window):
            sleep_for = min(max(0.05, window.window_seconds * random.uniform(0.2, 0.6)), max_sleep)
            time.sleep(sleep_for)

    @contextmanager
    def limit(self, key: str, limit: int, window_seconds: int):
        win = RateWindow(key=key, limit=limit, window_seconds=window_seconds)
        self.wait(win)
        yield


class LocalRateLimiter:
    # Simple fixed-window limiter; process-local, best-effort only.
    def __init__(self):
        self._buckets = {}

    def allow(self, window: RateWindow) -> bool:
        now = int(time.time())
        bucket = now // window.window_seconds
        key = (window.key, bucket)
        cnt = self._buckets.get(key, 0) + 1
        self._buckets[key] = cnt
        return cnt <= window.limit

    def wait(self, window: RateWindow, max_sleep: float = 5.0) -> None:
        while not self.allow(window):
            sleep_for = min(max(0.05, window.window_seconds * random.uniform(0.2, 0.6)), max_sleep)
            time.sleep(sleep_for)

    @contextmanager
    def limit(self, key: str, limit: int, window_seconds: int):
        win = RateWindow(key=key, limit=limit, window_seconds=window_seconds)
        self.wait(win)
        yield


def build_limiter(redis_url: Optional[str]):
    if redis_url and redis is not None:
        client = redis.from_url(redis_url)
        return RedisRateLimiter(client)
    return LocalRateLimiter()


def rps_to_window(rps: float) -> RateWindow:
    """Convert an RPS (can be fractional) to an integer token limit over a time window.

    We search small windows and pick the one with minimal error between
    tokens/window and desired rps, ensuring at least 1 token if rps>0.
    """
    if rps <= 0:
        # Zero means effectively disabled; use 1 token per very long window to throttle heavily
        return RateWindow(key="", limit=1, window_seconds=60)

    candidates = [1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30, 60]
    best = None
    best_err = float("inf")
    for w in candidates:
        tokens = max(1, round(rps * w))
        actual = tokens / w
        err = abs(actual - rps)
        if err < best_err:
            best_err = err
            best = (tokens, w)
    tokens, window_seconds = best  # type: ignore[misc]
    return RateWindow(key="", limit=int(tokens), window_seconds=int(window_seconds))

