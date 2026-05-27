# Scalability Tests

Tests the Star Predictor under load for two scenarios:
- **Single VM** — requests go directly to prod1 (no load balancer)
- **Two VMs** — requests go through NGINX which distributes across prod1 + prod2

## Setup (jump server)

```bash
python3 -m venv ~/locust-env
source ~/locust-env/bin/activate
pip install locust
cd src/tests
chmod +x run_tests.sh
```

## Run

```bash
./run_tests.sh <prod1-ip> <prod1-ip> <prod2-ip>
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

## Generating graphs

After running the tests, generate comparison graphs for p50, p95 and CPU usage across all user counts:

```bash
pip install matplotlib
python3 plot_results.py results/<timestamp>
```

If no path is given, the script automatically picks the most recent results folder.

Three PNG files are saved into the results folder:
- `p50_comparison.png` — median response time, 1 VM vs 2 VMs, for each user count
- `p95_comparison.png` — 95th percentile response time, 1 VM vs 2 VMs, for each user count
- `cpu_comparison.png` — container CPU usage, 1 VM vs 2 VMs, for each user count

Copy them to your local machine with:
```bash
scp -i ~/.ssh/<your-key> ubuntu@<jump-ip>:~/DE2-project/src/tests/results/<timestamp>/*.png .
```

## Notes

- Locust must be run inside a virtual environment to avoid system package conflicts
- The SSH key for docker stats collection is hardcoded to `~/.ssh/group1-key.pem` in `run_tests.sh` — update if your key has a different name
- The `/health` endpoint returns the container hostname, used to verify NGINX is distributing requests across both servers
