#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Scalability test runner — single VM vs two VMs (via NGINX)
#  Runs tests at 50, 100, and 200 concurrent users
#
#  Usage:
#    chmod +x run_tests.sh
#    ./run_tests.sh <prod1-ip> <nginx-ip> <prod2-ip>
# ═══════════════════════════════════════════════════════════════

PROD1_IP=${1:?  "Usage: $0 <prod1-ip> <nginx-ip> <prod2-ip>"}
NGINX_IP=${2:?  "Usage: $0 <prod1-ip> <nginx-ip> <prod2-ip>"}
PROD2_IP=${3:?  "Usage: $0 <prod1-ip> <nginx-ip> <prod2-ip>"}

PROD1_PORT=8000
NGINX_PORT=8888

RESULTS_DIR="results/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

SSH_KEY=~/.ssh/group1-key.pem
SSH_OPTS="-i $SSH_KEY -o StrictHostKeyChecking=no"

export PATH=$PATH:$HOME/.local/bin

SPAWN_RATE=10
DURATION=60s
USER_COUNTS=(50 100 200)

echo "================================================"
echo "  Star Predictor Scalability Tests"
echo "  Results will be saved to: $RESULTS_DIR"
echo "================================================"


# ── Helper: collect docker stats ──────────────────────────────
collect_stats() {
    local label=$1
    local server_ip=$2
    local duration=$3
    local outfile="$RESULTS_DIR/docker_stats_${label}.txt"

    ssh $SSH_OPTS ubuntu@$server_ip \
        "timeout $duration docker stats star_predictor_app --no-trunc --format \
        'table {{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}\t{{.NetIO}}'" \
        > "$outfile" 2>/dev/null &
    echo $!
}


# ── Helper: check load balancer distribution ──────────────────
check_lb_distribution() {
    local nginx_ip=$1
    local requests=50
    local outfile="$RESULTS_DIR/lb_distribution.txt"
    echo "--- Load balancer distribution ($requests requests to /health) ---" >> "$outfile"
    declare -A counts
    for i in $(seq 1 $requests); do
        server=$(curl -s http://$nginx_ip:$NGINX_PORT/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('server','unknown'))" 2>/dev/null)
        counts[$server]=$((${counts[$server]:-0} + 1))
    done
    for server in "${!counts[@]}"; do
        echo "  $server: ${counts[$server]} requests" >> "$outfile"
    done
    cat "$outfile"
}


# ════════════════════════════════════════════════════════════════
#  Loop through user counts
# ════════════════════════════════════════════════════════════════
for USERS in "${USER_COUNTS[@]}"; do

    echo ""
    echo "════════════════════════════════════════════════"
    echo "  Testing with $USERS concurrent users"
    echo "════════════════════════════════════════════════"

    # ── Single VM ──────────────────────────────────────────────
    echo ""
    echo "[Single VM] http://$PROD1_IP:$PROD1_PORT — $USERS users"

    STATS_PID=$(collect_stats "single_vm_${USERS}users" $PROD1_IP ${DURATION%s})

    locust -f locustfile.py \
        --host "http://$PROD1_IP:$PROD1_PORT" \
        --users $USERS \
        --spawn-rate $SPAWN_RATE \
        --run-time $DURATION \
        --headless \
        --csv "$RESULTS_DIR/single_vm_${USERS}users" \
        --csv-full-history \
        --html "$RESULTS_DIR/single_vm_${USERS}users_report.html" \
        2>&1 | tee "$RESULTS_DIR/single_vm_${USERS}users.log"

    wait $STATS_PID 2>/dev/null

    # Brief pause between tests
    echo "  Pausing 10s before next test..."
    sleep 10

    # ── Two VMs via NGINX ──────────────────────────────────────
    echo ""
    echo "[Two VMs]   http://$NGINX_IP:$NGINX_PORT — $USERS users"

    STATS_PID1=$(collect_stats "two_vm_prod1_${USERS}users" $PROD1_IP ${DURATION%s})
    STATS_PID2=$(collect_stats "two_vm_prod2_${USERS}users" $PROD2_IP ${DURATION%s})

    locust -f locustfile.py \
        --host "http://$NGINX_IP:$NGINX_PORT" \
        --users $USERS \
        --spawn-rate $SPAWN_RATE \
        --run-time $DURATION \
        --headless \
        --csv "$RESULTS_DIR/two_vm_${USERS}users" \
        --csv-full-history \
        --html "$RESULTS_DIR/two_vm_${USERS}users_report.html" \
        2>&1 | tee "$RESULTS_DIR/two_vm_${USERS}users.log"

    wait $STATS_PID1 $STATS_PID2 2>/dev/null

    echo "  Pausing 10s before next test..."
    sleep 10

done


# ════════════════════════════════════════════════════════════════
#  Load balancer distribution check
# ════════════════════════════════════════════════════════════════
echo ""
echo "Checking load balancer distribution..."
check_lb_distribution $NGINX_IP


# ════════════════════════════════════════════════════════════════
#  Summary
# ════════════════════════════════════════════════════════════════
echo ""
echo "================================================"
echo "  All tests complete. Results in: $RESULTS_DIR"
echo "================================================"
