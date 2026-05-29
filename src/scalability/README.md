# ML Scalability — Distributed Training Analysis

This component evaluates how the full model training pipeline scales across different Ray cluster sizes (1, 2, and 3 nodes), measuring wall-clock time and resource utilisation at each configuration.

---

## Overview

- **Goal:** Measure training pipeline speedup and resource usage as Ray cluster nodes are added
- **Configurations tested:** 1 node (2 CPUs), 2 nodes (4 CPUs), 3 nodes (6 CPUs)
- **Each configuration:** Run 3 times independently and averaged to reduce timing variance
- **Pipeline per run:** Full Optuna tuning for XGBoost, LightGBM, Random Forest (50 trials each, 5-fold CV) + retrain all 5 models + pick best

---

## Directory Structure

```
scalability/
├── scalability_train.py         # Full pipeline script with --nodes argument
├── scalability_results.json     # Accumulated results for all 3 node configurations
├── scalability_log.txt          # Timestamped log of all runs
├── best_model_1node.pkl         # Best model from 1-node run
├── best_model_2node.pkl         # Best model from 2-node run
└── best_model_3node.pkl         # Best model from 3-node run
```

---

## Setup

Same dependencies as the training component:
```bash
pip install ray[tune] optuna xgboost lightgbm scikit-learn pandas numpy psutil joblib
```

**For the bastion server (3-node run only), install Ray:**
```bash
pip install ray[tune] optuna xgboost lightgbm scikit-learn pandas numpy psutil joblib
ray --version   # verify
```

---

## Cluster Setup Per Configuration

### 1 node — dev1 only

```bash
# On dev2: stop Ray worker
ray stop

# On bastion: make sure Ray is not running
ray stop

# Verify on dev1 — should show 1 active node
ray status
```

### 2 nodes — dev1 + dev2

```bash
# On dev2: join cluster
ray start --address='dev1:6379'

# Verify on dev1 — should show 2 active nodes
ray status
```

### 3 nodes — dev1 + dev2 + bastion

```bash
# On bastion: join cluster
ray start --address='dev1:6379'

# Verify on dev1 — should show 3 active nodes
ray status
```

**Test connectivity before joining (run on bastion):**
```bash
nc -zv dev1 6379
```

---

## Running the Script

Run this on dev1 after setting up the correct cluster configuration:

```bash
cd /home/ubuntu/DE2-project/scalability

# 1-node run
python3 scalability_train.py --nodes 1

# 2-node run
python3 scalability_train.py --nodes 2

# 3-node run
python3 scalability_train.py --nodes 3
```

Each run appends its results to `scalability_results.json`. After all 3 runs, the script automatically prints a full comparison table to the terminal.

---

## Results

| Nodes | CPUs | Avg Total Time (s) | Speedup | CPU Mean (%) | RAM Peak (MB) |
|---|---|---|---|---|---|
| 1 | 2 | 1470 ± 30 | 1.00× | 79.5 | 3254 |
| 2 | 4 | 915 ± 42 | 1.61× | 65.3 | 3392 |
| 3 | 6 | 702 ± 12 | 2.09× | 53.3 | 3426 |

Per-model tuning times (averaged):

| Nodes | XGBoost (s) | LightGBM (s) | Random Forest (s) |
|---|---|---|---|
| 1 | 441 ± 9 | 443 ± 8 | 581 ± 24 |
| 2 | 283 ± 5 | 296 ± 1 | 331 ± 37 |
| 3 | 226 ± 5 | 226 ± 4 | 242 ± 7 |

---

## Output Files

| File | Description |
|---|---|
| `scalability_results.json` | Full results for all 3 node configs — timing, resource usage, per-run breakdowns, best model per config |
| `scalability_log.txt` | Complete timestamped log of every run across all configurations |
| `best_model_Xnode.pkl` | Best model (by RMSE) from each node configuration, loadable with `joblib.load()` |