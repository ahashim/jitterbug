"""
Jitterbug - Demonstrates the effect of adding jitter to cache TTLs.

Two sets of endpoints:
  /static/data?id={0..999}  - fixed 10s TTL
  /jitter/data?id={0..999}  - 10s + random(0..5s) TTL

On cache miss, simulates 20-50ms of expensive work.
Keys are cached lazily on first request and then refreshed on cache miss.

Uses prometheus_client multiprocess mode so metrics aggregate across workers.
"""

import asyncio
import json
import os
import random
import time
from contextlib import asynccontextmanager
from typing import Literal

import redis.asyncio as redis
import uvicorn
from fastapi import FastAPI, Query, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    REGISTRY,
    generate_latest,
    multiprocess,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REDIS_URL = "redis://redis:6379/0"
STATIC_TTL = 10  # seconds
MAX_JITTER = 5  # seconds  (so 10-15s range)
NUM_IDS = 1000
SIMULATE_WORK_MIN_SECONDS = 0.02  # 20ms
SIMULATE_WORK_MAX_SECONDS = 0.05  # 50ms

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
cache_hits = Counter(
    "cache_hits_total",
    "Total cache hits",
    ["mode"],
)
cache_misses = Counter(
    "cache_misses_total",
    "Total cache misses",
    ["mode"],
)
request_duration = Histogram(
    "request_duration_seconds",
    "Request latency in seconds",
    ["mode"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0),
)

Mode = Literal["static", "jitter"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get_redis() -> redis.Redis:
    """Return the Redis connection pool, raising if not yet initialized."""
    r: redis.Redis = app.state.redis
    return r


def _cache_key(mode: Mode, item_id: int) -> str:
    return f"{mode}:/data?id={item_id}"


def _ttl_ms(mode: Mode) -> int:
    if mode == "static":
        return STATIC_TTL * 1000
    jittered_ttl = STATIC_TTL + random.uniform(0, MAX_JITTER)
    return int(jittered_ttl * 1000)


async def _simulate_expensive_work(item_id: int) -> dict:
    """Simulate a slow upstream / computation."""
    await asyncio.sleep(
        random.uniform(SIMULATE_WORK_MIN_SECONDS, SIMULATE_WORK_MAX_SECONDS)
    )
    return {
        "id": item_id,
        "payload": f"result-for-{item_id}",
        "generated_at": time.time(),
    }


# ---------------------------------------------------------------------------
# App lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = redis.ConnectionPool.from_url(
        REDIS_URL, decode_responses=True, max_connections=2000
    )
    r = redis.Redis(connection_pool=pool)
    app.state.redis = r
    yield
    await r.aclose()


app = FastAPI(title="Jitterbug", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
async def _handle_request(mode: Mode, item_id: int) -> dict:
    """Core handler for both /static and /jitter endpoints."""
    start = time.perf_counter()
    r = _get_redis()

    cache_key = _cache_key(mode, item_id)
    cached = await r.get(cache_key)

    if cached is not None:
        cache_hits.labels(mode=mode).inc()
        result = json.loads(cached)
    else:
        cache_misses.labels(mode=mode).inc()
        result = await _simulate_expensive_work(item_id)
        serialized = json.dumps(result)
        await r.psetex(cache_key, _ttl_ms(mode), serialized)

    elapsed = time.perf_counter() - start
    request_duration.labels(mode=mode).observe(elapsed)
    return result


@app.get("/static/data")
async def static_data(id: int = Query(ge=0, lt=NUM_IDS)):
    return await _handle_request("static", id)


@app.get("/jitter/data")
async def jitter_data(id: int = Query(ge=0, lt=NUM_IDS)):
    return await _handle_request("jitter", id)


@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics for single- and multi-process modes."""
    if os.getenv("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
