# Scalability Tests

Tests the Star Predictor under load for two scenarios:
- **Single VM** — requests go directly to prod1 (no load balancer)
- **Two VMs** — requests go through NGINX which distributes across prod1 + prod2

## Setup (jump server)

```bash
pip install locust
cd src/tests
chmod +x run_tests.sh
```

## Run

```bash
./run_tests.sh <prod1-ip>:8000 <prod1-ip>:8888 <prod2-ip>:8000
```

## What gets measured

| Metric | Tool |
|---|---|
| Requests/sec (max throughput) | Locust CSV output |
| p50 / p95 / p99 latency | Locust CSV output |
| Failure rate | Locust CSV output |
| CPU and memory usage | `docker stats` on each server |
| Load balancer distribution | `/health` endpoint (returns hostname) |

## Parameters

Edit `run_tests.sh` to adjust:
```bash
USERS=50        # concurrent users
SPAWN_RATE=5    # users added per second during ramp-up
DURATION=60s    # how long to run each test
```

## Results

Each run creates a timestamped folder under `results/` containing:
- `single_vm_report.html` — open in browser for full charts
- `two_vm_report.html`
- `docker_stats_*.txt` — CPU/mem sampled during the test
- `lb_distribution.txt` — how many requests each server handled
