"""
predict.py — inference script for both the best individual model and the stacking ensemble.

Usage:
    python3 predict.py --input /path/to/data.csv --mode individual
    python3 predict.py --input /path/to/data.csv --mode ensemble
    python3 predict.py --input /path/to/data.csv --mode both

The input CSV must have the same feature columns used during training.
The target column (log_stars) does not need to be present.
Predictions are printed to terminal and saved as a CSV.
"""

import argparse
import json
import os
import joblib
import numpy as np
import pandas as pd
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
MODELS_DIR   = "/home/ubuntu/DE2-project/models"
ENSEMBLE_DIR = os.path.join(MODELS_DIR, "ensemble")

# ── Logger ────────────────────────────────────────────────────────────────────
def log(msg=""):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def log_section(title):
    log()
    log("=" * 60)
    log(f"  {title}")
    log("=" * 60)

# ── Load metadata ─────────────────────────────────────────────────────────────
def load_individual_metadata():
    path = os.path.join(MODELS_DIR, "best_individual_metadata.json")
    with open(path) as f:
        return json.load(f)

def load_ensemble_metadata():
    path = os.path.join(ENSEMBLE_DIR, "ensemble_metadata.json")
    with open(path) as f:
        return json.load(f)

# ── Predict: individual model ─────────────────────────────────────────────────
def predict_individual(X):
    log_section("INDIVIDUAL MODEL INFERENCE")
    meta = load_individual_metadata()

    model_name = meta["model_name"]
    model_file = os.path.join(MODELS_DIR, f"best_individual_model_{model_name}.pkl")
    log(f"Loading model : {model_file}")
    model = joblib.load(model_file)

    log(f"Model type    : {meta['model_type']} ({model_name})")
    log(f"Trained on    : {meta['train_size']} rows")
    log(f"Test RMSE     : {meta['metrics']['rmse']:.4f}")
    log(f"Test R2       : {meta['metrics']['r2']:.4f}")
    log(f"Input rows    : {len(X)}")

    # Validate features
    expected = meta["features"]
    missing  = [f for f in expected if f not in X.columns]
    extra    = [f for f in X.columns if f not in expected]
    if missing:
        raise ValueError(f"Input is missing features: {missing}")
    if extra:
        log(f"WARNING: extra columns ignored: {extra}")
    X = X[expected]

    preds = model.predict(X)
    log(f"Predictions complete — {len(preds)} rows")
    return preds, model_name

# ── Predict: ensemble ─────────────────────────────────────────────────────────
def predict_ensemble(X):
    log_section("ENSEMBLE MODEL INFERENCE")
    meta = load_ensemble_metadata()

    log(f"Ensemble type : {meta['ensemble_type']}")
    log(f"Base models   : {meta['base_models']}")
    log(f"Meta model    : {meta['meta_model']}")
    log(f"Test RMSE     : {meta['metrics']['rmse']:.4f}")
    log(f"Test R2       : {meta['metrics']['r2']:.4f}")
    log(f"Input rows    : {len(X)}")

    # Validate features
    expected = meta["features"]
    missing  = [f for f in expected if f not in X.columns]
    extra    = [f for f in X.columns if f not in expected]
    if missing:
        raise ValueError(f"Input is missing features: {missing}")
    if extra:
        log(f"WARNING: extra columns ignored: {extra}")
    X = X[expected]

    # Load and run each base model
    base_preds = []
    for name in meta["base_models"]:
        model_path = os.path.join(MODELS_DIR, meta["base_model_files"][name])
        log(f"Loading base model: {model_path}")
        m    = joblib.load(model_path)
        pred = m.predict(X)
        base_preds.append(pred)
        log(f"  {name:<22} predictions done  (sample: {pred[:3]})")

    # Stack and run meta-model
    stacked = np.column_stack(base_preds)
    log(f"Loading meta model: {os.path.join(ENSEMBLE_DIR, 'meta_model.pkl')}")
    meta_model = joblib.load(os.path.join(ENSEMBLE_DIR, "meta_model.pkl"))
    preds = meta_model.predict(stacked)

    log(f"Ensemble predictions complete — {len(preds)} rows")
    log("Meta-model weights applied:")
    for name, coef in zip(meta["base_models"], meta["meta_model_coefficients"].values()):
        log(f"  {name:<22} = {coef:.4f}")

    return preds, "ensemble"

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Run inference using trained models.")
    parser.add_argument("--input",  required=True, help="Path to input CSV file")
    parser.add_argument("--mode",   default="both", choices=["individual", "ensemble", "both"],
                        help="Which model to use for inference (default: both)")
    parser.add_argument("--output", default=None,
                        help="Path to save predictions CSV (default: auto-named in models dir)")
    args = parser.parse_args()

    log_section("PREDICT.PY — INFERENCE SCRIPT")
    log(f"Input file : {args.input}")
    log(f"Mode       : {args.mode}")
    log(f"Models dir : {MODELS_DIR}")

    # Load input
    log_section("LOADING INPUT DATA")
    df = pd.read_csv(args.input)
    log(f"Loaded {len(df)} rows, {df.shape[1]} columns")

    # Drop target column if present
    individual_meta = load_individual_metadata()
    target = individual_meta["target"]
    if target in df.columns:
        log(f"Target column '{target}' found in input — dropping it for inference")
        df = df.drop(columns=[target])

    results = df.copy()

    if args.mode in ("individual", "both"):
        preds, name = predict_individual(df)
        results[f"pred_{name}"] = preds
        log(f"Sample predictions ({name}): {preds[:5]}")

    if args.mode in ("ensemble", "both"):
        preds, name = predict_ensemble(df)
        results[f"pred_{name}"] = preds
        log(f"Sample predictions ({name}): {preds[:5]}")

    # Save output
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = args.output or os.path.join(MODELS_DIR, f"predictions_{args.mode}_{timestamp}.csv")
    results.to_csv(output_path, index=False)

    log_section("DONE")
    log(f"Predictions saved to: {output_path}")
    pred_cols = [c for c in results.columns if c.startswith("pred_")]
    for col in pred_cols:
        log(f"  {col}: min={results[col].min():.4f}  max={results[col].max():.4f}  mean={results[col].mean():.4f}")

if __name__ == "__main__":
    main()