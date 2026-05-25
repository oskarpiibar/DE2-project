"""
Scalability Test Graph Generator
==================================
Run from src/tests/ folder:
    python3 plot_results.py results/<timestamp>

Generates 3 graphs saved as PNG in the results folder:
    1. p50_comparison.png  — p50 response time over time, 1 vs 2 VMs, all user counts
    2. p95_comparison.png  — p95 response time over time, 1 vs 2 VMs, all user counts
    3. cpu_comparison.png  — CPU usage over time, 1 vs 2 VMs, all user counts
"""

import sys
import os
import csv
import re
import glob
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
USER_COUNTS = [50, 100, 200, 400]
COLORS = {
    "single": ["#2563eb", "#1d4ed8", "#1e3a8a"],   # blue shades
    "two":    ["#16a34a", "#15803d", "#14532d"],    # green shades
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def read_history_csv(path):
    """Read a locust _stats_history.csv and return lists of (timestamp, p50, p95)."""
    times, p50s, p95s = [], [], []
    if not os.path.exists(path):
        return times, p50s, p95s
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only use the Aggregated row
            if row.get("Name", "").strip() != "Aggregated":
                continue
            try:
                times.append(float(row["Timestamp"]))
                p50s.append(float(row.get("50%", row.get("Median Response Time", 0)) or 0))
                p95s.append(float(row.get("95%", 0) or 0))
            except (ValueError, KeyError):
                continue
    # Normalise timestamps to start at 0
    if times:
        t0 = times[0]
        times = [t - t0 for t in times]
    return times, p50s, p95s


def read_docker_stats(path):
    """Parse docker stats txt file, return (times, cpu_pcts)."""
    times, cpus = [], []
    if not os.path.exists(path):
        return times, cpus
    t = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            # Skip header lines
            if line.startswith("CPU") or not line:
                continue
            # Extract first percentage found
            match = re.search(r'([\d.]+)%', line)
            if match:
                cpus.append(float(match.group(1)))
                times.append(t)
                t += 1
    return times, cpus


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main(results_dir):
    if not os.path.isdir(results_dir):
        print(f"Directory not found: {results_dir}")
        sys.exit(1)

    fig1, axes1 = plt.subplots(1, 4, figsize=(20, 4), sharey=False)
    fig2, axes2 = plt.subplots(1, 4, figsize=(20, 4), sharey=False)
    fig3, axes3 = plt.subplots(1, 4, figsize=(20, 4), sharey=False)

    for idx, users in enumerate(USER_COUNTS):
        ax_p50 = axes1[idx]
        ax_p95 = axes2[idx]
        ax_cpu = axes3[idx]

        # ── Locust history ──────────────────────────────────────
        single_hist = os.path.join(results_dir, f"single_vm_{users}users_stats_history.csv")
        two_hist    = os.path.join(results_dir, f"two_vm_{users}users_stats_history.csv")

        t_s, p50_s, p95_s = read_history_csv(single_hist)
        t_t, p50_t, p95_t = read_history_csv(two_hist)

        # Trim to same length to avoid shape mismatch
        n_s = min(len(t_s), len(p50_s), len(p95_s))
        n_t = min(len(t_t), len(p50_t), len(p95_t))
        t_s, p50_s, p95_s = t_s[:n_s], p50_s[:n_s], p95_s[:n_s]
        t_t, p50_t, p95_t = t_t[:n_t], p50_t[:n_t], p95_t[:n_t]

        # p50 plot
        if t_s:
            ax_p50.plot(t_s, p50_s, color=COLORS["single"][idx], label="1 VM", linewidth=2)
        if t_t:
            ax_p50.plot(t_t, p50_t, color=COLORS["two"][idx],    label="2 VMs", linewidth=2)
        ax_p50.set_title(f"{users} users")
        ax_p50.set_xlabel("Time (s)")
        ax_p50.set_ylabel("Response time (ms)")
        ax_p50.legend()
        ax_p50.grid(True, alpha=0.3)

        # p95 plot
        if t_s:
            ax_p95.plot(t_s, p95_s, color=COLORS["single"][idx], label="1 VM", linewidth=2)
        if t_t:
            ax_p95.plot(t_t, p95_t, color=COLORS["two"][idx],    label="2 VMs", linewidth=2)
        ax_p95.set_title(f"{users} users")
        ax_p95.set_xlabel("Time (s)")
        ax_p95.set_ylabel("Response time (ms)")
        ax_p95.legend()
        ax_p95.grid(True, alpha=0.3)

        # ── Docker CPU stats ────────────────────────────────────
        single_cpu_path = os.path.join(results_dir, f"docker_stats_single_vm_{users}users.txt")
        prod1_cpu_path  = os.path.join(results_dir, f"docker_stats_two_vm_prod1_{users}users.txt")
        prod2_cpu_path  = os.path.join(results_dir, f"docker_stats_two_vm_prod2_{users}users.txt")

        t_sc, cpu_sc   = read_docker_stats(single_cpu_path)
        t_p1, cpu_p1   = read_docker_stats(prod1_cpu_path)
        t_p2, cpu_p2   = read_docker_stats(prod2_cpu_path)

        if t_sc:
            ax_cpu.plot(t_sc, cpu_sc, color=COLORS["single"][idx], label="1 VM",       linewidth=2)
        if t_p1:
            ax_cpu.plot(t_p1, cpu_p1, color=COLORS["two"][idx],    label="2 VMs prod1", linewidth=2, linestyle="--")
        if t_p2:
            ax_cpu.plot(t_p2, cpu_p2, color="#86efac",              label="2 VMs prod2", linewidth=2, linestyle=":")
        ax_cpu.set_title(f"{users} users")
        ax_cpu.set_xlabel("Time (s)")
        ax_cpu.set_ylabel("CPU usage (%)")
        ax_cpu.legend()
        ax_cpu.grid(True, alpha=0.3)

    # ── Titles and save ─────────────────────────────────────────
    fig1.suptitle("p50 Response Time — 1 VM vs 2 VMs", fontsize=14, fontweight="bold")
    fig2.suptitle("p95 Response Time — 1 VM vs 2 VMs", fontsize=14, fontweight="bold")
    fig3.suptitle("CPU Usage — 1 VM vs 2 VMs",          fontsize=14, fontweight="bold")

    for fig in [fig1, fig2, fig3]:
        fig.tight_layout()

    out1 = os.path.join(results_dir, "p50_comparison.png")
    out2 = os.path.join(results_dir, "p95_comparison.png")
    out3 = os.path.join(results_dir, "cpu_comparison.png")

    fig1.savefig(out1, dpi=150)
    fig2.savefig(out2, dpi=150)
    fig3.savefig(out3, dpi=150)

    print(f"Saved: {out1}")
    print(f"Saved: {out2}")
    print(f"Saved: {out3}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Auto-find the most recent results folder
        folders = sorted(glob.glob("results/2*"))
        if not folders:
            print("Usage: python3 plot_results.py results/<timestamp>")
            sys.exit(1)
        results_dir = folders[-1]
        print(f"Using most recent results: {results_dir}")
    else:
        results_dir = sys.argv[1]

    main(results_dir)
