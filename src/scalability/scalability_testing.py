import ray
from ray import tune
from ray.tune.schedulers import ASHAScheduler
from ray.tune.search.optuna import OptunaSearch

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, KFold
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import xgboost as xgb
import lightgbm as lgb
import joblib
import json
import os
import time
import argparse
import threading
import psutil
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DATA_PATH    = "/home/ubuntu/DE2-project/data/processed/features.csv"
TARGET       = "log_stars"
OUTPUT_DIR   = "/home/ubuntu/DE2-project/src/scalability"
LOG_FILE     = os.path.join(OUTPUT_DIR, "scalability_log.txt")
RESULTS_FILE = os.path.join(OUTPUT_DIR, "scalability_results.json")
NUM_SAMPLES  = 50
CV_FOLDS     = 5
RANDOM_SEED  = 42
NUM_RUNS     = 3   # averaged runs per node configuration
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Args ──────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--nodes", type=int, required=True, choices=[1, 2, 3],
                    help="Number of Ray nodes currently active in the cluster")
args = parser.parse_args()
NUM_NODES = args.nodes

# ── Logger ────────────────────────────────────────────────────────────────────
def log(msg=""):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def log_section(title):
    bar = "=" * 60
    log(); log(bar); log(f"  {title}"); log(bar)

def log_metrics(name, metrics, marker=""):
    log(f"  {name:<22}  RMSE={metrics['rmse']:.4f}  MAE={metrics['mae']:.4f}  R2={metrics['r2']:.4f}{marker}")

# ── Resource monitor (runs in background thread) ──────────────────────────────
class ResourceMonitor:
    def __init__(self, interval=0.5):
        self.interval   = interval
        self.cpu_pcts   = []
        self.ram_pcts   = []
        self.ram_mbs    = []
        self._stop      = threading.Event()
        self._thread    = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join()

    def _run(self):
        while not self._stop.is_set():
            self.cpu_pcts.append(psutil.cpu_percent(interval=None))
            mem = psutil.virtual_memory()
            self.ram_pcts.append(mem.percent)
            self.ram_mbs.append(mem.used / 1024 / 1024)
            time.sleep(self.interval)

    def summary(self):
        return {
            "cpu_mean_pct":  round(float(np.mean(self.cpu_pcts)), 2)  if self.cpu_pcts else 0,
            "cpu_max_pct":   round(float(np.max(self.cpu_pcts)), 2)   if self.cpu_pcts else 0,
            "ram_mean_pct":  round(float(np.mean(self.ram_pcts)), 2)  if self.ram_pcts else 0,
            "ram_peak_pct":  round(float(np.max(self.ram_pcts)), 2)   if self.ram_pcts else 0,
            "ram_peak_mb":   round(float(np.max(self.ram_mbs)), 2)    if self.ram_mbs  else 0,
            "ram_mean_mb":   round(float(np.mean(self.ram_mbs)), 2)   if self.ram_mbs  else 0,
            "samples_taken": len(self.cpu_pcts),
        }

# ── Metric helper ─────────────────────────────────────────────────────────────
def get_metrics(model, X, y):
    preds = model.predict(X)
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, preds))),
        "mae":  float(mean_absolute_error(y, preds)),
        "r2":   float(r2_score(y, preds)),
    }

# ── Load data once (outside runs) ────────────────────────────────────────────
log_section(f"SCALABILITY RUN — {NUM_NODES} NODE(S)")
log(f"Timestamp  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log(f"Nodes      : {NUM_NODES}")
log(f"Runs       : {NUM_RUNS} (will be averaged)")
log(f"Trials     : {NUM_SAMPLES} per model per run")
log(f"CV folds   : {CV_FOLDS}")
log(f"Data       : {DATA_PATH}")

ray.init(address="auto")
cluster_resources = ray.cluster_resources()
log(f"Cluster CPUs    : {cluster_resources.get('CPU', 0)}")
log(f"Cluster RAM (GB): {round(cluster_resources.get('memory', 0) / 1e9, 2)}")
log(f"Cluster nodes   : {len([n for n in ray.nodes() if n['Alive']])}")

df   = pd.read_csv(DATA_PATH)
X    = df.drop(columns=[TARGET])
y    = df[TARGET]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=RANDOM_SEED)
log(f"Train: {len(X_train)}  Test: {len(X_test)}  Features: {X.shape[1]}")

kf = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)

# ── Model factory functions ───────────────────────────────────────────────────
def make_xgboost(config):
    return xgb.XGBRegressor(
        n_estimators=config["n_estimators"], max_depth=config["max_depth"],
        learning_rate=config["learning_rate"], subsample=config["subsample"],
        colsample_bytree=config["colsample_bytree"],
        colsample_bylevel=config["colsample_bylevel"],
        reg_alpha=config["reg_alpha"], reg_lambda=config["reg_lambda"],
        min_child_weight=config["min_child_weight"], gamma=config["gamma"],
        random_state=RANDOM_SEED, n_jobs=1, verbosity=0,
    )

def make_lightgbm(config):
    return lgb.LGBMRegressor(
        n_estimators=config["n_estimators"], max_depth=config["max_depth"],
        learning_rate=config["learning_rate"], num_leaves=config["num_leaves"],
        subsample=config["subsample"], colsample_bytree=config["colsample_bytree"],
        reg_alpha=config["reg_alpha"], reg_lambda=config["reg_lambda"],
        min_child_samples=config["min_child_samples"],
        random_state=RANDOM_SEED, n_jobs=1, verbose=-1,
    )

def make_random_forest(config):
    return RandomForestRegressor(
        n_estimators=config["n_estimators"], max_depth=config["max_depth"],
        max_features=config["max_features"],
        min_samples_leaf=config["min_samples_leaf"],
        min_samples_split=config["min_samples_split"],
        random_state=RANDOM_SEED, n_jobs=1,
    )

# ── CV scoring for Ray Tune ───────────────────────────────────────────────────
def cv_score(model_fn, config):
    fold_rmses = []
    for tr_idx, va_idx in kf.split(X_train):
        m = model_fn(config)
        m.fit(X_train.iloc[tr_idx], y_train.iloc[tr_idx])
        preds = m.predict(X_train.iloc[va_idx])
        fold_rmses.append(float(np.sqrt(mean_squared_error(y_train.iloc[va_idx], preds))))
    return float(np.mean(fold_rmses)), float(np.std(fold_rmses))

def train_xgboost(config):
    mean_rmse, std_rmse = cv_score(make_xgboost, config)
    tune.report({"rmse": mean_rmse, "rmse_std": std_rmse, "done": True})

def train_lightgbm(config):
    mean_rmse, std_rmse = cv_score(make_lightgbm, config)
    tune.report({"rmse": mean_rmse, "rmse_std": std_rmse, "done": True})

def train_random_forest(config):
    mean_rmse, std_rmse = cv_score(make_random_forest, config)
    tune.report({"rmse": mean_rmse, "rmse_std": std_rmse, "done": True})

# ── Search spaces ─────────────────────────────────────────────────────────────
xgb_space = {
    "n_estimators":      tune.choice([200, 400, 600, 800, 1000]),
    "max_depth":         tune.choice([2, 3, 4, 5, 6, 7, 9]),
    "learning_rate":     tune.loguniform(0.005, 0.3),
    "subsample":         tune.uniform(0.6, 1.0),
    "colsample_bytree":  tune.uniform(0.5, 1.0),
    "colsample_bylevel": tune.uniform(0.5, 1.0),
    "reg_alpha":         tune.loguniform(1e-4, 10.0),
    "reg_lambda":        tune.loguniform(1e-4, 10.0),
    "min_child_weight":  tune.choice([1, 3, 5, 7, 10]),
    "gamma":             tune.loguniform(1e-4, 1.0),
}
lgb_space = {
    "n_estimators":      tune.choice([200, 400, 600, 800, 1000]),
    "max_depth":         tune.choice([2, 3, 4, 5, 6, 9, 12]),
    "learning_rate":     tune.loguniform(0.005, 0.3),
    "num_leaves":        tune.choice([20, 31, 40, 60, 80, 120]),
    "subsample":         tune.uniform(0.6, 1.0),
    "colsample_bytree":  tune.uniform(0.5, 1.0),
    "reg_alpha":         tune.loguniform(1e-4, 10.0),
    "reg_lambda":        tune.loguniform(1e-4, 10.0),
    "min_child_samples": tune.choice([5, 10, 20, 30, 50]),
}
rf_space = {
    "n_estimators":      tune.choice([200, 400, 600, 800]),
    "max_depth":         tune.choice([3, 5, 7, 10, None]),
    "max_features":      tune.choice(["sqrt", "log2", 0.5, 0.7]),
    "min_samples_leaf":  tune.choice([1, 2, 4, 8]),
    "min_samples_split": tune.choice([2, 5, 10, 15]),
}

# ── Single full pipeline run ──────────────────────────────────────────────────
def run_full_pipeline(run_idx):
    log(f"")
    log(f"  ── Run {run_idx + 1} of {NUM_RUNS} ──────────────────────────────")
    monitor = ResourceMonitor(interval=0.5)
    monitor.start()
    t_start = time.perf_counter()

    # Tune XGBoost
    log(f"  [Run {run_idx+1}] Tuning XGBoost...")
    t0 = time.perf_counter()
    xgb_tuner = tune.Tuner(
        tune.with_resources(train_xgboost, {"cpu": 1}),
        param_space=xgb_space,
        tune_config=tune.TuneConfig(
            metric="rmse", mode="min", num_samples=NUM_SAMPLES,
            scheduler=ASHAScheduler(max_t=10, grace_period=2),
            search_alg=OptunaSearch(metric="rmse", mode="min"),
        ),
    )
    xgb_res     = xgb_tuner.fit()
    best_xgb    = xgb_res.get_best_result().config
    xgb_tune_t  = round(time.perf_counter() - t0, 2)
    log(f"  [Run {run_idx+1}] XGBoost done in {xgb_tune_t}s  best CV RMSE={xgb_res.get_best_result().metrics['rmse']:.4f}")

    # Tune LightGBM
    log(f"  [Run {run_idx+1}] Tuning LightGBM...")
    t0 = time.perf_counter()
    lgb_tuner = tune.Tuner(
        tune.with_resources(train_lightgbm, {"cpu": 1}),
        param_space=lgb_space,
        tune_config=tune.TuneConfig(
            metric="rmse", mode="min", num_samples=NUM_SAMPLES,
            scheduler=ASHAScheduler(max_t=10, grace_period=2),
            search_alg=OptunaSearch(metric="rmse", mode="min"),
        ),
    )
    lgb_res     = lgb_tuner.fit()
    best_lgb    = lgb_res.get_best_result().config
    lgb_tune_t  = round(time.perf_counter() - t0, 2)
    log(f"  [Run {run_idx+1}] LightGBM done in {lgb_tune_t}s  best CV RMSE={lgb_res.get_best_result().metrics['rmse']:.4f}")

    # Tune Random Forest
    log(f"  [Run {run_idx+1}] Tuning Random Forest...")
    t0 = time.perf_counter()
    rf_tuner = tune.Tuner(
        tune.with_resources(train_random_forest, {"cpu": 1}),
        param_space=rf_space,
        tune_config=tune.TuneConfig(
            metric="rmse", mode="min", num_samples=NUM_SAMPLES,
            scheduler=ASHAScheduler(max_t=10, grace_period=2),
            search_alg=OptunaSearch(metric="rmse", mode="min"),
        ),
    )
    rf_res      = rf_tuner.fit()
    best_rf     = rf_res.get_best_result().config
    rf_tune_t   = round(time.perf_counter() - t0, 2)
    log(f"  [Run {run_idx+1}] Random Forest done in {rf_tune_t}s  best CV RMSE={rf_res.get_best_result().metrics['rmse']:.4f}")

    # Retrain all models on full train set
    log(f"  [Run {run_idx+1}] Retraining final models...")
    t0 = time.perf_counter()

    all_models = {}

    m = make_xgboost(best_xgb)
    m.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    all_models["xgboost"] = {"metrics": get_metrics(m, X_test, y_test), "params": best_xgb, "model": m}

    m = make_lightgbm(best_lgb)
    m.fit(X_train, y_train)
    all_models["lightgbm"] = {"metrics": get_metrics(m, X_test, y_test), "params": best_lgb, "model": m}

    m = make_random_forest(best_rf)
    m.fit(X_train, y_train)
    all_models["random_forest"] = {"metrics": get_metrics(m, X_test, y_test), "params": best_rf, "model": m}

    ridge = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])
    ridge.fit(X_train, y_train)
    all_models["ridge"] = {"metrics": get_metrics(ridge, X_test, y_test), "params": {"alpha": 1.0}, "model": ridge}

    en = Pipeline([("scaler", StandardScaler()), ("model", ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=RANDOM_SEED))])
    en.fit(X_train, y_train)
    all_models["elasticnet"] = {"metrics": get_metrics(en, X_test, y_test), "params": {"alpha": 0.1, "l1_ratio": 0.5}, "model": en}

    retrain_t = round(time.perf_counter() - t0, 2)

    # Pick best
    best_name   = min(all_models, key=lambda n: all_models[n]["metrics"]["rmse"])
    best        = all_models[best_name]
    total_time  = round(time.perf_counter() - t_start, 2)

    monitor.stop()
    resources = monitor.summary()

    log(f"  [Run {run_idx+1}] Retrain done in {retrain_t}s")
    log(f"  [Run {run_idx+1}] Total time: {total_time}s")
    log(f"  [Run {run_idx+1}] Best model: {best_name}  RMSE={best['metrics']['rmse']:.4f}  R2={best['metrics']['r2']:.4f}")
    log(f"  [Run {run_idx+1}] CPU mean={resources['cpu_mean_pct']}%  peak={resources['cpu_max_pct']}%")
    log(f"  [Run {run_idx+1}] RAM mean={resources['ram_mean_mb']}MB  peak={resources['ram_peak_mb']}MB")

    return {
        "run_index":       run_idx + 1,
        "total_time_s":    total_time,
        "xgb_tune_time_s": xgb_tune_t,
        "lgb_tune_time_s": lgb_tune_t,
        "rf_tune_time_s":  rf_tune_t,
        "retrain_time_s":  retrain_t,
        "resources":       resources,
        "best_model_name": best_name,
        "best_metrics":    best["metrics"],
        "best_params":     best["params"],
        "all_model_scores": {
            n: {"rmse": v["metrics"]["rmse"], "mae": v["metrics"]["mae"], "r2": v["metrics"]["r2"]}
            for n, v in all_models.items()
        },
        "models_obj": all_models,  # kept in memory only, not serialised
    }

# ── Run NUM_RUNS times and average ────────────────────────────────────────────
log_section(f"STARTING {NUM_RUNS} PIPELINE RUNS ON {NUM_NODES} NODE(S)")

run_results = []
for i in range(NUM_RUNS):
    result = run_full_pipeline(i)
    run_results.append(result)

ray.shutdown()
log("Ray shut down")

# ── Average across runs ───────────────────────────────────────────────────────
log_section("AVERAGING RESULTS ACROSS RUNS")

def avg(key, nested=None):
    if nested:
        return round(float(np.mean([r[key][nested] for r in run_results])), 4)
    return round(float(np.mean([r[key] for r in run_results])), 4)

def std_dev(key):
    return round(float(np.std([r[key] for r in run_results])), 4)

averaged = {
    "total_time_s":    {"mean": avg("total_time_s"),    "std": std_dev("total_time_s")},
    "xgb_tune_time_s": {"mean": avg("xgb_tune_time_s"), "std": std_dev("xgb_tune_time_s")},
    "lgb_tune_time_s": {"mean": avg("lgb_tune_time_s"), "std": std_dev("lgb_tune_time_s")},
    "rf_tune_time_s":  {"mean": avg("rf_tune_time_s"),  "std": std_dev("rf_tune_time_s")},
    "retrain_time_s":  {"mean": avg("retrain_time_s"),  "std": std_dev("retrain_time_s")},
    "cpu_mean_pct":    {"mean": avg("resources", "cpu_mean_pct"), "std": round(float(np.std([r["resources"]["cpu_mean_pct"] for r in run_results])), 4)},
    "cpu_max_pct":     {"mean": avg("resources", "cpu_max_pct"),  "std": round(float(np.std([r["resources"]["cpu_max_pct"]  for r in run_results])), 4)},
    "ram_peak_mb":     {"mean": avg("resources", "ram_peak_mb"),  "std": round(float(np.std([r["resources"]["ram_peak_mb"]  for r in run_results])), 4)},
    "ram_mean_mb":     {"mean": avg("resources", "ram_mean_mb"),  "std": round(float(np.std([r["resources"]["ram_mean_mb"]  for r in run_results])), 4)},
}

# Best model from last run (most recent tuning result)
last          = run_results[-1]
best_name     = last["best_model_name"]
best_metrics  = last["best_metrics"]
best_params   = last["best_params"]
best_model_obj= last["models_obj"][best_name]["model"]

log(f"Averaged over {NUM_RUNS} runs:")
log(f"  Total time     : {averaged['total_time_s']['mean']}s  (std={averaged['total_time_s']['std']}s)")
log(f"  XGBoost tune   : {averaged['xgb_tune_time_s']['mean']}s")
log(f"  LightGBM tune  : {averaged['lgb_tune_time_s']['mean']}s")
log(f"  RF tune        : {averaged['rf_tune_time_s']['mean']}s")
log(f"  Retrain        : {averaged['retrain_time_s']['mean']}s")
log(f"  CPU mean       : {averaged['cpu_mean_pct']['mean']}%")
log(f"  CPU peak       : {averaged['cpu_max_pct']['mean']}%")
log(f"  RAM peak       : {averaged['ram_peak_mb']['mean']} MB")
log(f"  Best model     : {best_name}  RMSE={best_metrics['rmse']:.4f}  R2={best_metrics['r2']:.4f}")

# ── Save best model for this node config ──────────────────────────────────────
log_section("SAVING BEST MODEL")

model_path = os.path.join(OUTPUT_DIR, f"best_model_{NUM_NODES}node.pkl")
joblib.dump(best_model_obj, model_path)
log(f"Saved model : {model_path}")

# ── Load existing results file and append this node config ───────────────────
if os.path.exists(RESULTS_FILE):
    with open(RESULTS_FILE) as f:
        all_results = json.load(f)
    log(f"Loaded existing results file — appending node={NUM_NODES} data")
else:
    all_results = {}
    log("No existing results file — creating new one")

all_results[f"{NUM_NODES}_nodes"] = {
    "num_nodes":        NUM_NODES,
    "num_runs":         NUM_RUNS,
    "num_samples":      NUM_SAMPLES,
    "cv_folds":         CV_FOLDS,
    "cluster_cpus":     cluster_resources.get("CPU", 0),
    "cluster_ram_gb":   round(cluster_resources.get("memory", 0) / 1e9, 2),
    "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "averaged_metrics": averaged,
    "per_run_details": [
        {
            "run":             r["run_index"],
            "total_time_s":    r["total_time_s"],
            "xgb_tune_time_s": r["xgb_tune_time_s"],
            "lgb_tune_time_s": r["lgb_tune_time_s"],
            "rf_tune_time_s":  r["rf_tune_time_s"],
            "retrain_time_s":  r["retrain_time_s"],
            "best_model":      r["best_model_name"],
            "best_metrics":    r["best_metrics"],
            "resources":       r["resources"],
            "all_model_scores":r["all_model_scores"],
        }
        for r in run_results
    ],
    "best_model": {
        "name":    best_name,
        "type":    "xgboost" if best_name == "xgboost" else ("lightgbm" if best_name == "lightgbm" else "sklearn"),
        "params":  best_params,
        "metrics": best_metrics,
        "file":    f"best_model_{NUM_NODES}node.pkl",
    },
    "features": list(X.columns),
    "target":   TARGET,
}

with open(RESULTS_FILE, "w") as f:
    json.dump(all_results, f, indent=2)
log(f"Saved results : {RESULTS_FILE}")

# ── Print comparison if all 3 node configs are done ──────────────────────────
if len(all_results) == 3:
    log_section("FULL SCALABILITY COMPARISON (all 3 configs complete)")
    log(f"  {'Nodes':<8}  {'CPUs':<6}  {'Avg Time (s)':<14}  {'Std':<8}  {'CPU%':>6}  {'RAM MB':>8}  {'Best Model':<15}  {'RMSE':>8}  {'R2':>8}")
    log(f"  {'-'*8}  {'-'*6}  {'-'*14}  {'-'*8}  {'-'*6}  {'-'*8}  {'-'*15}  {'-'*8}  {'-'*8}")
    for k in ["1_nodes", "2_nodes", "3_nodes"]:
        if k not in all_results:
            continue
        r   = all_results[k]
        avg_t = r["averaged_metrics"]["total_time_s"]["mean"]
        std_t = r["averaged_metrics"]["total_time_s"]["std"]
        cpu   = r["averaged_metrics"]["cpu_mean_pct"]["mean"]
        ram   = r["averaged_metrics"]["ram_peak_mb"]["mean"]
        bm    = r["best_model"]
        log(f"  {r['num_nodes']:<8}  {int(r['cluster_cpus']):<6}  {avg_t:<14}  {std_t:<8}  {cpu:>6}  {ram:>8}  {bm['name']:<15}  {bm['metrics']['rmse']:>8.4f}  {bm['metrics']['r2']:>8.4f}")

log_section("DONE")
log(f"Output directory : {OUTPUT_DIR}")
log(f"  best_model_{NUM_NODES}node.pkl")
log(f"  scalability_results.json  (node={NUM_NODES} added)")
log(f"  scalability_log.txt")