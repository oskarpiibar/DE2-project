import ray
from ray import tune
from ray.tune.schedulers import ASHAScheduler
from ray.tune.search.optuna import OptunaSearch

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, KFold, cross_val_predict
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
from sklearn.ensemble import RandomForestRegressor, StackingRegressor
from sklearn.linear_model import Ridge, ElasticNet
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
import xgboost as xgb
import lightgbm as lgb
import joblib
import json
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DATA_PATH   = "/home/ubuntu/DE2-project/data/processed/features.csv"
TARGET      = "log_stars"
OUTPUT_DIR  = "/home/ubuntu/DE2-project/models"
ENSEMBLE_DIR= os.path.join(OUTPUT_DIR, "ensemble")
LOG_FILE    = os.path.join(OUTPUT_DIR, "training_log.txt")
NUM_SAMPLES = 50
CV_FOLDS    = 5
RANDOM_SEED = 42
# ─────────────────────────────────────────────────────────────────────────────

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ENSEMBLE_DIR, exist_ok=True)

# ── Logger ────────────────────────────────────────────────────────────────────
def log(msg=""):
    ts   = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def log_section(title):
    bar = "=" * 60
    log()
    log(bar)
    log(f"  {title}")
    log(bar)

def log_metrics(name, metrics, marker=""):
    log(f"  {name:<22}  RMSE={metrics['rmse']:.4f}  MAE={metrics['mae']:.4f}  R2={metrics['r2']:.4f}{marker}")

def get_metrics(model, X, y):
    preds = model.predict(X)
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, preds))),
        "mae":  float(mean_absolute_error(y, preds)),
        "r2":   float(r2_score(y, preds)),
    }

def get_metrics_from_preds(preds, y):
    return {
        "rmse": float(np.sqrt(mean_squared_error(y, preds))),
        "mae":  float(mean_absolute_error(y, preds)),
        "r2":   float(r2_score(y, preds)),
    }

# ── Start ─────────────────────────────────────────────────────────────────────
log_section("TRAINING RUN STARTED")
log(f"Timestamp  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
log(f"Data       : {DATA_PATH}")
log(f"Target     : {TARGET}")
log(f"CV Folds   : {CV_FOLDS}")
log(f"Tune trials: {NUM_SAMPLES} per model")
log(f"Search     : OptunaSearch (Bayesian)")
log(f"Output     : {OUTPUT_DIR}")
log(f"Ensemble   : {ENSEMBLE_DIR}")

# ── Ray init ──────────────────────────────────────────────────────────────────
log_section("RAY INIT")
ray.init(address="auto")
log("Connected to Ray cluster")

# ── Load data ─────────────────────────────────────────────────────────────────
log_section("DATA LOADING")
df = pd.read_csv(DATA_PATH)
log(f"Loaded {len(df)} rows, {df.shape[1]} columns")

X = df.drop(columns=[TARGET])
y = df[TARGET]
log(f"Features   : {X.shape[1]}")
log(f"Target     : {TARGET}  (min={y.min():.3f}, max={y.max():.3f}, mean={y.mean():.3f}, std={y.std():.3f})")

X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=RANDOM_SEED
)
log(f"Train size : {len(X_train)}  |  Test size: {len(X_test)}")
log(f"Feature list: {list(X.columns)}")

# ── Ray Tune training functions (with CV) ─────────────────────────────────────
kf = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)

def cv_score(model_fn, config):
    """Run k-fold CV and return mean RMSE across folds."""
    fold_rmses = []
    fold_r2s   = []
    for fold_idx, (tr_idx, va_idx) in enumerate(kf.split(X_train)):
        X_tr, X_va = X_train.iloc[tr_idx], X_train.iloc[va_idx]
        y_tr, y_va = y_train.iloc[tr_idx], y_train.iloc[va_idx]
        model = model_fn(config)
        model.fit(X_tr, y_tr)
        preds = model.predict(X_va)
        rmse  = float(np.sqrt(mean_squared_error(y_va, preds)))
        r2    = float(r2_score(y_va, preds))
        fold_rmses.append(rmse)
        fold_r2s.append(r2)
    return np.mean(fold_rmses), np.mean(fold_r2s), np.std(fold_rmses)

def make_xgboost(config):
    return xgb.XGBRegressor(
        n_estimators     = config["n_estimators"],
        max_depth        = config["max_depth"],
        learning_rate    = config["learning_rate"],
        subsample        = config["subsample"],
        colsample_bytree = config["colsample_bytree"],
        colsample_bylevel= config["colsample_bylevel"],
        reg_alpha        = config["reg_alpha"],
        reg_lambda       = config["reg_lambda"],
        min_child_weight = config["min_child_weight"],
        gamma            = config["gamma"],
        random_state=RANDOM_SEED, n_jobs=1, verbosity=0,
    )

def make_lightgbm(config):
    return lgb.LGBMRegressor(
        n_estimators     = config["n_estimators"],
        max_depth        = config["max_depth"],
        learning_rate    = config["learning_rate"],
        num_leaves       = config["num_leaves"],
        subsample        = config["subsample"],
        colsample_bytree = config["colsample_bytree"],
        reg_alpha        = config["reg_alpha"],
        reg_lambda       = config["reg_lambda"],
        min_child_samples= config["min_child_samples"],
        random_state=RANDOM_SEED, n_jobs=1, verbose=-1,
    )

def make_random_forest(config):
    return RandomForestRegressor(
        n_estimators  = config["n_estimators"],
        max_depth     = config["max_depth"],
        max_features  = config["max_features"],
        min_samples_leaf  = config["min_samples_leaf"],
        min_samples_split = config["min_samples_split"],
        random_state=RANDOM_SEED, n_jobs=1,
    )

def train_xgboost(config):
    mean_rmse, mean_r2, std_rmse = cv_score(make_xgboost, config)
    tune.report({"rmse": mean_rmse, "r2": mean_r2, "rmse_std": std_rmse, "done": True})

def train_lightgbm(config):
    mean_rmse, mean_r2, std_rmse = cv_score(make_lightgbm, config)
    tune.report({"rmse": mean_rmse, "r2": mean_r2, "rmse_std": std_rmse, "done": True})

def train_random_forest(config):
    mean_rmse, mean_r2, std_rmse = cv_score(make_random_forest, config)
    tune.report({"rmse": mean_rmse, "r2": mean_r2, "rmse_std": std_rmse, "done": True})

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

# ── Tune XGBoost ──────────────────────────────────────────────────────────────
log_section(f"RAY TUNE — XGBOOST  ({NUM_SAMPLES} trials, {CV_FOLDS}-fold CV, Optuna search)")
log("Starting XGBoost hyperparameter search...")

xgb_tuner = tune.Tuner(
    tune.with_resources(train_xgboost, {"cpu": 1}),
    param_space=xgb_space,
    tune_config=tune.TuneConfig(
        metric="rmse",
        mode="min",
        num_samples=NUM_SAMPLES,
        scheduler=ASHAScheduler(max_t=10, grace_period=2),
        search_alg=OptunaSearch(metric="rmse", mode="min"),
    ),
)
xgb_results   = xgb_tuner.fit()
best_xgb_cfg  = xgb_results.get_best_result().config
best_xgb_meta = xgb_results.get_best_result().metrics

log("XGBoost tuning complete")
log(f"  CV mean RMSE : {best_xgb_meta['rmse']:.4f}")
log(f"  CV mean R2   : {best_xgb_meta['r2']:.4f}")
log(f"  CV RMSE std  : {best_xgb_meta['rmse_std']:.4f}")
log("  Best hyperparameters:")
for k, v in best_xgb_cfg.items():
    log(f"    {k:<24} = {v}")

# ── Tune LightGBM ─────────────────────────────────────────────────────────────
log_section(f"RAY TUNE — LIGHTGBM  ({NUM_SAMPLES} trials, {CV_FOLDS}-fold CV, Optuna search)")
log("Starting LightGBM hyperparameter search...")

lgb_tuner = tune.Tuner(
    tune.with_resources(train_lightgbm, {"cpu": 1}),
    param_space=lgb_space,
    tune_config=tune.TuneConfig(
        metric="rmse",
        mode="min",
        num_samples=NUM_SAMPLES,
        scheduler=ASHAScheduler(max_t=10, grace_period=2),
        search_alg=OptunaSearch(metric="rmse", mode="min"),
    ),
)
lgb_results   = lgb_tuner.fit()
best_lgb_cfg  = lgb_results.get_best_result().config
best_lgb_meta = lgb_results.get_best_result().metrics

log("LightGBM tuning complete")
log(f"  CV mean RMSE : {best_lgb_meta['rmse']:.4f}")
log(f"  CV mean R2   : {best_lgb_meta['r2']:.4f}")
log(f"  CV RMSE std  : {best_lgb_meta['rmse_std']:.4f}")
log("  Best hyperparameters:")
for k, v in best_lgb_cfg.items():
    log(f"    {k:<24} = {v}")

# ── Tune Random Forest ────────────────────────────────────────────────────────
log_section(f"RAY TUNE — RANDOM FOREST  ({NUM_SAMPLES} trials, {CV_FOLDS}-fold CV, Optuna search)")
log("Starting Random Forest hyperparameter search...")

rf_tuner = tune.Tuner(
    tune.with_resources(train_random_forest, {"cpu": 1}),
    param_space=rf_space,
    tune_config=tune.TuneConfig(
        metric="rmse",
        mode="min",
        num_samples=NUM_SAMPLES,
        scheduler=ASHAScheduler(max_t=10, grace_period=2),
        search_alg=OptunaSearch(metric="rmse", mode="min"),
    ),
)
rf_results   = rf_tuner.fit()
best_rf_cfg  = rf_results.get_best_result().config
best_rf_meta = rf_results.get_best_result().metrics

log("Random Forest tuning complete")
log(f"  CV mean RMSE : {best_rf_meta['rmse']:.4f}")
log(f"  CV mean R2   : {best_rf_meta['r2']:.4f}")
log(f"  CV RMSE std  : {best_rf_meta['rmse_std']:.4f}")
log("  Best hyperparameters:")
for k, v in best_rf_cfg.items():
    log(f"    {k:<24} = {v}")

ray.shutdown()
log("Ray shut down")

# ── Retrain all base models on full training set ───────────────────────────────
log_section("RETRAINING FINAL BASE MODELS ON FULL TRAIN SET")
all_models = {}

log("Retraining XGBoost with best config...")
xgb_final = make_xgboost(best_xgb_cfg)
xgb_final.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
metrics = get_metrics(xgb_final, X_test, y_test)
all_models["xgboost"] = {"model": xgb_final, "metrics": metrics, "params": best_xgb_cfg, "type": "xgboost"}
log_metrics("xgboost", metrics)

log("Retraining LightGBM with best config...")
lgb_final = make_lightgbm(best_lgb_cfg)
lgb_final.fit(X_train, y_train)
metrics = get_metrics(lgb_final, X_test, y_test)
all_models["lightgbm"] = {"model": lgb_final, "metrics": metrics, "params": best_lgb_cfg, "type": "lightgbm"}
log_metrics("lightgbm", metrics)

log("Retraining Random Forest with best config...")
rf_final = make_random_forest(best_rf_cfg)
rf_final.fit(X_train, y_train)
metrics = get_metrics(rf_final, X_test, y_test)
all_models["random_forest"] = {"model": rf_final, "metrics": metrics, "params": best_rf_cfg, "type": "sklearn"}
log_metrics("random_forest", metrics)

log("Training Ridge baseline...")
ridge_final = Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))])
ridge_final.fit(X_train, y_train)
metrics = get_metrics(ridge_final, X_test, y_test)
all_models["ridge"] = {"model": ridge_final, "metrics": metrics, "params": {"alpha": 1.0}, "type": "sklearn"}
log_metrics("ridge", metrics)

log("Training ElasticNet baseline...")
en_final = Pipeline([("scaler", StandardScaler()), ("model", ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=RANDOM_SEED))])
en_final.fit(X_train, y_train)
metrics = get_metrics(en_final, X_test, y_test)
all_models["elasticnet"] = {"model": en_final, "metrics": metrics, "params": {"alpha": 0.1, "l1_ratio": 0.5}, "type": "sklearn"}
log_metrics("elasticnet", metrics)

# ── Build stacking ensemble (out-of-fold) ─────────────────────────────────────
log_section("BUILDING STACKING ENSEMBLE (OUT-OF-FOLD)")
log(f"Generating out-of-fold predictions using {CV_FOLDS}-fold CV...")
log("This ensures the meta-model never sees predictions made on data it was trained on.")

base_model_fns = {
    "xgboost":      lambda: make_xgboost(best_xgb_cfg),
    "lightgbm":     lambda: make_lightgbm(best_lgb_cfg),
    "random_forest":lambda: make_random_forest(best_rf_cfg),
    "ridge":        lambda: Pipeline([("scaler", StandardScaler()), ("model", Ridge(alpha=1.0))]),
    "elasticnet":   lambda: Pipeline([("scaler", StandardScaler()), ("model", ElasticNet(alpha=0.1, l1_ratio=0.5, random_state=RANDOM_SEED))]),
}

# Out-of-fold predictions on train set (for meta-model training)
oof_preds = np.zeros((len(X_train), len(base_model_fns)))
log("Generating OOF predictions per fold:")

for fold_idx, (tr_idx, va_idx) in enumerate(kf.split(X_train)):
    X_tr, X_va = X_train.iloc[tr_idx], X_train.iloc[va_idx]
    y_tr        = y_train.iloc[tr_idx]
    log(f"  Fold {fold_idx+1}/{CV_FOLDS} — train={len(tr_idx)} rows, val={len(va_idx)} rows")
    for col_idx, (name, model_fn) in enumerate(base_model_fns.items()):
        m = model_fn()
        m.fit(X_tr, y_tr)
        oof_preds[va_idx, col_idx] = m.predict(X_va)
    log(f"  Fold {fold_idx+1} done")

log("OOF predictions complete")

# Test set predictions from fully-retrained base models (for meta-model evaluation)
test_preds = np.column_stack([
    all_models["xgboost"]["model"].predict(X_test),
    all_models["lightgbm"]["model"].predict(X_test),
    all_models["random_forest"]["model"].predict(X_test),
    all_models["ridge"]["model"].predict(X_test),
    all_models["elasticnet"]["model"].predict(X_test),
])
log("Test set predictions from final base models stacked")

# Train meta-model on OOF predictions
log("Training meta-model (Ridge) on OOF predictions...")
meta_model = Ridge(alpha=1.0)
meta_model.fit(oof_preds, y_train)

# Evaluate ensemble on test set
ensemble_test_preds = meta_model.predict(test_preds)
ensemble_metrics = get_metrics_from_preds(ensemble_test_preds, y_test)

log("Meta-model training complete")
log(f"  Meta-model coefficients (weight per base model):")
for name, coef in zip(base_model_fns.keys(), meta_model.coef_):
    log(f"    {name:<22} = {coef:.4f}")
log(f"  Meta-model intercept     = {meta_model.intercept_:.4f}")
log("Ensemble test set performance:")
log_metrics("ensemble", ensemble_metrics)

# ── Full model comparison ─────────────────────────────────────────────────────
log_section("FULL MODEL COMPARISON (test set)")
log(f"  {'Model':<22}  {'RMSE':>8}  {'MAE':>8}  {'R2':>8}")
log(f"  {'-'*22}  {'-'*8}  {'-'*8}  {'-'*8}")

all_scores = {name: d["metrics"] for name, d in all_models.items()}
all_scores["ensemble"] = ensemble_metrics
sorted_scores = sorted(all_scores.items(), key=lambda x: x[1]["rmse"])

for rank, (name, m) in enumerate(sorted_scores):
    marker = "  <-- BEST" if rank == 0 else ""
    log(f"  {name:<22}  {m['rmse']:>8.4f}  {m['mae']:>8.4f}  {m['r2']:>8.4f}{marker}")

# ── Pick best individual model ────────────────────────────────────────────────
best_individual_name = sorted(all_models.items(), key=lambda x: x[1]["metrics"]["rmse"])[0][0]
best_individual      = all_models[best_individual_name]

log_section("BEST INDIVIDUAL MODEL")
log(f"Name : {best_individual_name}")
log(f"RMSE : {best_individual['metrics']['rmse']:.4f}")
log(f"MAE  : {best_individual['metrics']['mae']:.4f}")
log(f"R2   : {best_individual['metrics']['r2']:.4f}")
if best_individual["params"]:
    log("Hyperparameters:")
    for k, v in best_individual["params"].items():
        log(f"  {k:<24} = {v}")

log_section("ENSEMBLE MODEL")
log(f"RMSE : {ensemble_metrics['rmse']:.4f}")
log(f"MAE  : {ensemble_metrics['mae']:.4f}")
log(f"R2   : {ensemble_metrics['r2']:.4f}")
improvement = best_individual['metrics']['rmse'] - ensemble_metrics['rmse']
log(f"RMSE improvement over best individual: {improvement:.4f}")

# ── Save individual base models (for ensemble loading) ────────────────────────
log_section("SAVING ALL FILES")

base_model_names = ["xgboost", "lightgbm", "random_forest", "ridge", "elasticnet"]
for name in base_model_names:
    path = os.path.join(ENSEMBLE_DIR, f"{name}.pkl")
    joblib.dump(all_models[name]["model"], path)
    log(f"Saved ensemble base model : {path}")

meta_path = os.path.join(ENSEMBLE_DIR, "meta_model.pkl")
joblib.dump(meta_model, meta_path)
log(f"Saved meta model          : {meta_path}")

# Save best individual model
individual_path = os.path.join(OUTPUT_DIR, f"best_individual_model_{best_individual_name}.pkl")
joblib.dump(best_individual["model"], individual_path)
log(f"Saved best individual     : {individual_path}")

# Save individual metadata
individual_metadata = {
    "model_name":      best_individual_name,
    "model_type":      best_individual["type"],
    "features":        list(X.columns),
    "target":          TARGET,
    "hyperparameters": best_individual["params"],
    "metrics": {
        "rmse": best_individual["metrics"]["rmse"],
        "mae":  best_individual["metrics"]["mae"],
        "r2":   best_individual["metrics"]["r2"],
    },
    "train_size":  len(X_train),
    "test_size":   len(X_test),
    "cv_folds":    CV_FOLDS,
    "num_samples": NUM_SAMPLES,
    "all_model_scores": {
        name: {"rmse": v["rmse"], "mae": v["mae"], "r2": v["r2"]}
        for name, v in all_scores.items()
    },
}
individual_meta_path = os.path.join(OUTPUT_DIR, "best_individual_metadata.json")
with open(individual_meta_path, "w") as f:
    json.dump(individual_metadata, f, indent=2)
log(f"Saved individual metadata : {individual_meta_path}")

# Save ensemble metadata
ensemble_metadata = {
    "ensemble_type":   "stacking",
    "meta_model":      "Ridge(alpha=1.0)",
    "oof_folds":       CV_FOLDS,
    "base_models":     base_model_names,
    "base_model_files": {name: f"ensemble/{name}.pkl" for name in base_model_names},
    "meta_model_file": "ensemble/meta_model.pkl",
    "meta_model_coefficients": dict(zip(base_model_names, meta_model.coef_.tolist())),
    "meta_model_intercept": float(meta_model.intercept_),
    "features":        list(X.columns),
    "target":          TARGET,
    "metrics": {
        "rmse": ensemble_metrics["rmse"],
        "mae":  ensemble_metrics["mae"],
        "r2":   ensemble_metrics["r2"],
    },
    "train_size":  len(X_train),
    "test_size":   len(X_test),
    "base_model_hyperparameters": {
        "xgboost":      best_xgb_cfg,
        "lightgbm":     best_lgb_cfg,
        "random_forest":best_rf_cfg,
        "ridge":        {"alpha": 1.0},
        "elasticnet":   {"alpha": 0.1, "l1_ratio": 0.5},
    },
    "all_model_scores": {
        name: {"rmse": v["rmse"], "mae": v["mae"], "r2": v["r2"]}
        for name, v in all_scores.items()
    },
}
ensemble_meta_path = os.path.join(ENSEMBLE_DIR, "ensemble_metadata.json")
with open(ensemble_meta_path, "w") as f:
    json.dump(ensemble_metadata, f, indent=2)
log(f"Saved ensemble metadata   : {ensemble_meta_path}")
log(f"Saved training log        : {LOG_FILE}")

log_section("ALL DONE")
log(f"Files saved to: {OUTPUT_DIR}")
log(f"  best_individual_model_{best_individual_name}.pkl")
log(f"  best_individual_metadata.json")
log(f"  ensemble/")
for name in base_model_names:
    log(f"    {name}.pkl")
log(f"    meta_model.pkl")
log(f"    ensemble_metadata.json")
log(f"  training_log.txt")