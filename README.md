# Jitterbug

A small load-testing setup that demonstrates the effect of cache TTL jitter.

- `GET /static/data?id=N` uses a fixed 10s TTL.
- `GET /jitter/data?id=N` uses a 10-15s TTL (`10s + random jitter`).

Both endpoints cache full responses in Redis by URL, including query parameters.
Locust drives high traffic and Grafana visualizes misses and latency.

## Requirements

- Docker
- Docker Compose (v2, `docker compose`)
- Open ports: `3000` (Grafana), `8000` (web), `8428` (VictoriaMetrics), `6379` (Redis)

## Instructions

1. Start the stack:

   ```bash
   docker compose up -d --build
   ```

2. Open Grafana:
   - URL: `http://localhost:3000`
   - The dashboard is pre-provisioned and loads automatically.

3. Let the test run:
   - Load generation runs headless for 10 minutes by default.
   - Compare static vs jitter on cache misses and latency panels.

4. (Optional) Run another cycle:

   ```bash
   docker compose restart loadgen
   ```

5. Stop everything:

   ```bash
   docker compose down
   ```

6. Stop and remove metrics volume:

   ```bash
   docker compose down -v
   ```
