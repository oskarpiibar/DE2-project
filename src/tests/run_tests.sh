#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Scalability test runner — single VM vs two VMs (via NGINX)
#
#  Usage:
#    chmod +x run_tests.sh
#    ./run_tests.sh <prod1-ip> <nginx-ip> <prod2-ip>
#
#  Example:
#    ./run_tests.sh 192.168.2.10 192.168.2.20 192.168.2.30
#
#  Requirements on the jump server:
#    pip install locust
# ═══════════════════════════════════════════════════════════════

PROD1_IP=${1:?  "Usage: $0 <prod1-ip> <nginx-ip> <prod2-ip>"}
NGINX_IP=${2:?  "Usage: $0 <prod1-ip> <nginx-ip> <prod2-ip>"}
PROD2_IP=${3:?  "Usage: $0 <prod1-ip> <nginx-ip> <prod2-ip>"}

RESULTS_DIR="results/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

USERS=50          # concurrent users
SPAWN_RATE=5      # users added per second
DURATION=60s      # test duration

SSH_KEY=~/.ssh/group1-key   # adjust if your key has a different name
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no"

echo "================================================"
echo "  Star Predictor Scalability Tests"
echo "  Results will be saved to: $RESULTS_DIR"
echo "================================================"


# ── Helper: collect docker stats from a server for N seconds ─────────────
collect_stats() {
    local label=$1
    local server_ip=$2
    local duration=$3
    local outfile="$RESULTS_DIR/docker_stats_${label}.txt"

    echo "  Collecting docker stats from $server_ip..."
    ssh $SSH_OPTS ubuntu@$server_ip \
        "timeout $duration docker stats star_predictor_app --no-trunc --format \
        'table {{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}'" \
        > "$outfile" 2>/dev/null &
    echo $!   # return PID so we can wait for it
}


# ── Helper: check load balancer distribution ─────────────────────────────
check_lb_distribution() {
    local nginx_ip=$1
    local requests=100
    echo ""
    echo "--- Load balancer distribution ($requests requests to /health) ---"
    declare -A counts
    for i in $(seq 1 $requests); do
        server=$(curl -s http://$nginx_ip/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('server','unknown'))" 2>/dev/null)
        counts[$server]=$((${counts[$server]:-0} + 1))
    done
    for server in "${!counts[@]}"; do
        echo "  $server: ${counts[$server]} requests"
    done
    echo "" 
} 


# ════════════════════════════════════════════════════════════════
#  TEST 1 — Single VM (prod1 direct, no NGINX)
# ════════════════════════════════════════════════════════════════
echo ""
echo "[1/2] Running single VM test against http://$PROD1_IP:8000"
echo "      Users: $USERS | Spawn rate: $SPAWN_RATE/s | Duration: $DURATION"
echo ""

# Start docker stats collection in background
STATS_PID=$(collect_stats "single_vm" $PROD1_IP ${DURATION%s})

# Run Locust
locust -f locustfile.py \
    --host "http://$PROD1_IP:8000" \
    --users $USERS \
    --spawn-rate $SPAWN_RATE \
    --run-time $DURATION \
    --headless \
    --csv "$RESULTS_DIR/single_vm" \
    --csv-full-history \
    --html "$RESULTS_DIR/single_vm_report.html" \
    2>&1 | tee "$RESULTS_DIR/single_vm_locust.log"

wait $STATS_PID 2>/dev/null
echo "  Single VM test done."


# ════════════════════════════════════════════════════════════════
#  TEST 2 — Two VMs via NGINX load balancer
# ════════════════════════════════════════════════════════════════
echo ""
echo "[2/2] Running two VM test against http://$NGINX_IP (NGINX)"
echo "      Users: $USERS | Spawn rate: $SPAWN_RATE/s | Duration: $DURATION"
echo ""

# Collect stats from both prod servers simultaneously
STATS_PID1=$(collect_stats "two_vm_prod1" $PROD1_IP ${DURATION%s})
STATS_PID2=$(collect_stats "two_vm_prod2" $PROD2_IP ${DURATION%s})

locust -f locustfile.py \
    --host "http://$NGINX_IP" \
    --users $USERS \
    --spawn-rate $SPAWN_RATE \
    --run-time $DURATION \
    --headless \
    --csv "$RESULTS_DIR/two_vm" \
    --csv-full-history \
    --html "$RESULTS_DIR/two_vm_report.html" \
    2>&1 | tee "$RESULTS_DIR/two_vm_locust.log"

wait $STATS_PID1 $STATS_PID2 2>/dev/null
echo "  Two VM test done."


# ════════════════════════════════════════════════════════════════
#  Load balancer distribution check
# ════════════════════════════════════════════════════════════════
check_lb_distribution $NGINX_IP >> "$RESULTS_DIR/lb_distribution.txt"
cat "$RESULTS_DIR/lb_distribution.txt"


# ════════════════════════════════════════════════════════════════
#  Summary
# ════════════════════════════════════════════════════════════════
echo ""
echo "================================================"
echo "  All tests complete. Results in: $RESULTS_DIR"
echo ""
echo "  Files generated:"
echo "    single_vm_stats.csv        — request stats per second"
echo "    single_vm_report.html      — full Locust HTML report"
echo "    docker_stats_single_vm.txt — CPU/mem on prod1"
echo ""
echo "    two_vm_stats.csv           — request stats per second"
echo "    two_vm_report.html         — full Locust HTML report"
echo "    docker_stats_two_vm_prod1  — CPU/mem on prod1"
echo "    docker_stats_two_vm_prod2  — CPU/mem on prod2"
echo ""
echo "    lb_distribution.txt        — requests per server via NGINX"
echo "================================================"
